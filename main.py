import requests
import logging
import csv
from typing import Dict, Optional, List
from time import sleep
from datetime import datetime, timezone

# ============================================================
# CONFIG
# ============================================================
CITIES = [
    {"name": "Chittagong", "lat": 22.34, "lon": 91.83},
    {"name": "Dhaka",      "lat": 23.81, "lon": 90.41},
    {"name": "Sylhet",     "lat": 24.89, "lon": 91.87},
    {"name": "Khulna",     "lat": 22.85, "lon": 89.54},
]

BASE_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_VARS = "temperature_2m,wind_speed_10m,relative_humidity_2m"

MAX_RETRIES = 3
cleaned_rows: List[Dict] = []
failed: List[str] = []
CSV_FILE = "weather_data.csv"
# ============================================================

# Logging setup (console + file)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("api_to_csv.log"),
        logging.StreamHandler()
    ],
)


RETRYABLE_STATUS = {429, 500, 502, 503, 504}

def fetch_city(city: Dict) -> Optional[Dict]:
    """Fetch current weather for one city. Retries only errors that may succeed later."""
    params = {"latitude": city["lat"], "longitude": city["lon"], "current": CURRENT_VARS}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(BASE_URL, params=params, timeout=10)
        except (requests.Timeout, requests.ConnectionError) as e:
            error = f"{type(e).__name__}: {e}"
        else:
            if response.ok:
                logging.info(f"Successfully fetched data for {city['name']}")
                return response.json()
            if response.status_code not in RETRYABLE_STATUS:
                logging.error(
                    f"{city['name']}: HTTP {response.status_code}, not retrying. "
                    f"Response: {response.text[:200]}"
                )
                return None
            error = f"HTTP {response.status_code}"

        if attempt < MAX_RETRIES:
            wait = 2 ** (attempt - 1)  # 1s, 2s, 4s...
            logging.warning(f"Attempt {attempt}/{MAX_RETRIES} failed for {city['name']} ({error}). Retrying in {wait}s...")
            sleep(wait)
        else:
            logging.error(f"All {MAX_RETRIES} attempts failed for {city['name']} ({error})")

    return None


def clean_data(city: Dict, api_response: Dict) -> Dict:
    """
    Flatten the nested JSON into a clean, flat dict.
    - Explicit type conversion
    - Safe .get() for missing fields
    - Sensible rounding for floats
    """
    current = api_response.get("current", {})

    # Our own fetch timestamp (UTC)
    fetched_at = datetime.now(timezone.utc).isoformat()

    def round_or_none(value, digits=1):
        return round(float(value), digits) if value is not None else None
    

    cleaned = {
        "city": city.get("name", "Unknown"),
        "temperature_c": round_or_none(current.get("temperature_2m")),
        "wind_speed_kmh": round_or_none(current.get("wind_speed_10m")),
        "humidity_pct": int(current["relative_humidity_2m"]) if current.get("relative_humidity_2m") is not None else None,
        "api_timestamp": current.get("time", ""),
        "fetched_at": fetched_at,
    }

    return cleaned


def save_to_csv(rows: List[Dict], filename: str = CSV_FILE) -> None:
    """Save a list of flat dicts to CSV using csv.DictWriter."""
    if not rows:
        logging.warning("No data to write to CSV")
        return

    fieldnames = [
        "city",
        "temperature_c",
        "wind_speed_kmh",
        "humidity_pct",
        "api_timestamp",
        "fetched_at",
    ]

    try:
        with open(filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        logging.info(f"Successfully wrote {len(rows)} rows to {filename}")
    except OSError as e:
        logging.error(f"Failed to write CSV: {e}")


def main():
    logging.info("Starting weather data fetch from Open-Meteo")

    cleaned_rows: List[Dict] = []

    for city in CITIES:
        logging.info(f"Summary: {len(cleaned_rows)} succeeded, {len(failed)} failed")
        if failed:
            logging.warning(f"Failed cities: {', '.join(failed)}")
        data = fetch_city(city)

        if data is None:
            failed.append(city["name"])
            continue

        cleaned = clean_data(city, data)
        cleaned_rows.append(cleaned)

        logging.info(
            f"{cleaned['city']} → "
            f"Temp: {cleaned['temperature_c']}°C | "
            f"Wind: {cleaned['wind_speed_kmh']} km/h | "
            f"Humidity: {cleaned['humidity_pct']}% | "
            f"API time: {cleaned['api_timestamp']}"
        )

    save_to_csv(cleaned_rows)
    


if __name__ == "__main__":
    main()