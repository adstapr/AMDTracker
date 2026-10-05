import json
import os
import sys
from bs4 import BeautifulSoup
import requests

# Path to your JSON file
JSON_FILE = "drivers.json"


def fetch_amd_release_notes(version):
  # Format version dots to hyphens: "22.10.2" -> "22-10-2"
  formatted_version = version.replace(".", "-")
  url = f"https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-{formatted_version}.html"

  print(f"Fetching release notes from: {url}")
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
  }

  response = requests.get(url, headers=headers)
  if response.status_code != 200:
    print(
        f"Error: Failed to fetch page (Status code: {response.status_code})"
    )
    sys.exit(1)

  soup = BeautifulSoup(response.text, "html.parser")

  # Extract Fixed Issues (AMD layout typically groups these under headings/lists)
  fixed_issues = []
  # Find sections containing fixed issues text in AMD's layout structure
  for header in soup.find_all(["h2", "h3", "strong"]):
    if "Fixed Issues" in header.text:
      # Extract subsequent list items until the next heading
      sibling = header.find_next_sibling()
      while sibling and sibling.name not in ["h2", "h3"]:
        if sibling.name == "ul":
          for li in sibling.find_all("li"):
            fixed_issues.append(li.text.strip())
        sibling = sibling.find_next_sibling()
      break

  return {
      "version": version,
      "url": url,
      "fixed_issues": (
          fixed_issues
          if fixed_issues
          else ["Could not parse automatically. Check manually."]
      ),
  }


def update_json(new_driver_data):
  if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r") as f:
      data = json.load(f)
  else:
    data = {"drivers": []}

  # Check if version already exists, update or append
  existing = next(
      (d for d in data["drivers"] if d["version"] == new_driver_data["version"]),
      None,
  )
  if existing:
    existing.update(new_driver_data)
    print(f"Updated existing entry for version {new_driver_data['version']}")
  else:
    data["drivers"].insert(0, new_driver_data)  # Add to top of list
    print(f"Added new entry for version {new_driver_data['version']}")

  with open(JSON_FILE, "w") as f:
    json.dump(data, f, indent=4)


if __name__ == "__main__":
  # Pass version as command-line argument
  if len(sys.argv) < 2:
    print("Usage: python update_drivers.py <version>")
    sys.exit(1)

  target_version = sys.argv[1]
  driver_info = fetch_amd_release_notes(target_version)
  update_json(driver_info)
