import json
import os
import sys
from bs4 import BeautifulSoup
import requests

JSON_FILE = "drivers.json"


def fetch_amd_release_notes(url):
  print(f"Processing release notes from: {url}")
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "en-US,en;q=0.9",
  }

  fixed_issues = []
  try:
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
      soup = BeautifulSoup(response.text, "html.parser")
      for header in soup.find_all(["h2", "h3", "strong"]):
        if "Fixed Issues" in header.text:
          sibling = header.find_next_sibling()
          while sibling and sibling.name not in ["h2", "h3"]:
            if sibling.name == "ul":
              for li in sibling.find_all("li"):
                fixed_issues.append(li.text.strip())
            sibling = sibling.find_next_sibling()
          break
    else:
      print(
          f"Warning: Received status code {response.status_code}. Bypassing"
          " scraper and saving URL directly."
      )
  except Exception as e:
    print(
        f"Notice: Could not scrape text due to network/bot protection ({e})."
        " Saving URL fallback."
    )

  # Extract version from URL string (e.g., RN-RAD-WIN-22-10-2.html -> 22.10.2)
  filename = url.split("/")[-1].replace(".html", "")
  parts = filename.replace("RN-RAD-WIN-", "").replace("-", ".")
  version = parts.split("-")[
      0
  ]  # fallback or clean extraction if possible

  return {
      "url": url,
      "fixed_issues": (
          fixed_issues
          if fixed_issues
          else ["Link added automatically. Manual review required."]
      ),
  }


def update_json(new_driver_data):
  if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r") as f:
      data = json.load(f)
  else:
    data = {"drivers": []}

  # Avoid duplicates based on URL
  data["drivers"] = [
      d for d in data["drivers"] if d["url"] != new_driver_data["url"]
  ]
  data["drivers"].insert(0, new_driver_data)

  with open(JSON_FILE, "w") as f:
    json.dump(data, f, indent=4)
  print("Successfully updated drivers.json")


if __name__ == "__main__":
  if len(sys.argv) < 2:
    print("Usage: python update_drivers.py <amd_url>")
    sys.exit(1)

  target_url = sys.argv[1]
  driver_info = fetch_amd_release_notes(target_url)
  update_json(driver_info)
