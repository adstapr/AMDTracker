import json
import os
import re
import sys
from bs4 import BeautifulSoup
import requests

JSON_FILE = "drivers.json"


def clean_text(text):
  """Cleans up smart quotes, trademark glitches, and weird spacing."""
  if not text:
    return ""
  # Fix common mojibake/encoding corruptions from web scraping
  text = (
      text.replace("â„¢", "™")
      .replace("â€“", "-")
      .replace("â€"


def parse_list_items(soup, header_keywords):
  """Scrapes text items under headings containing specific keywords."""
  items = []
  for header in soup.find_all(["h2", "h3", "strong", "p"]):
    text_content = header.get_text()
    if any(keyword.lower() in text_content.lower() for keyword in header_keywords):
      sibling = header.find_next_sibling()
      while sibling and sibling.name not in ["h2", "h3"]:
        if sibling.name == "ul":
          for li in sibling.find_all("li"):
            cleaned = clean_text(li.get_text())
            if cleaned:
              items.append(cleaned)
        sibling = sibling.find_next_sibling()
      if items:
        break
  return items


def fetch_amd_release_notes(url):
  print(f"Fetching release notes from: {url}")
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "en-US,en;q=0.9",
  }

  fixed_texts = []
  known_texts = []
  driver_type = "Optional"

  try:
    response = requests.get(url, headers=headers, timeout=10)
    # FORCE proper UTF-8 decoding so symbols like ™ don't break
    response.encoding = "utf-8"

    if response.status_code == 200:
      soup = BeautifulSoup(response.text, "html.parser")
      fixed_texts = parse_list_items(soup, ["Fixed Issues"])
      known_texts = parse_list_items(soup, ["Known Issues"])

      if "Recommended" in soup.get_text():
        driver_type = "Recommended"
  except Exception as e:
    print(f"Notice: Could not scrape text due to network restrictions ({e}).")

  # Extract version from filename
  filename = url.split("/")[-1].replace(".html", "")
  raw_version_part = filename.replace("RN-RAD-WIN-", "")
  version_match = re.search(r"(\d+-\d+-\d+)", raw_version_part)
  if version_match:
    version = version_match.group(1).replace("-", ".")
  else:
    version = raw_version_part.replace("-", ".")

  return {
      "version": version,
      "type": driver_type,
      "url": url,
      "fixed_texts": fixed_texts,
      "known_texts": known_texts,
  }


def update_json(scraped_data):
  if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r", encoding="utf-8") as f:
      data = json.load(f)
  else:
    data = {"drivers": [], "master_bugs": {}}

  master_bugs = data.setdefault("master_bugs", {})

  def process_bug_list(text_list):
    bug_ids = []
    for text in text_list:
      # Check if exact text already exists in master_bugs (ignoring case/spacing differences)
      existing_id = next(
          (k for k, v in master_bugs.items() if clean_text(v) == clean_text(text)),
          None,
      )
      if existing_id:
        bug_ids.append(existing_id)
      else:
        new_id = get_next_bug_id(master_bugs)
        master_bugs[new_id] = text
        bug_ids.append(new_id)
    return bug_ids

  fixed_bug_ids = process_bug_list(scraped_data["fixed_texts"])
  known_bug_ids = process_bug_list(scraped_data["known_texts"])

  new_driver_entry = {
      "version": scraped_data["version"],
      "type": scraped_data["type"],
      "url": scraped_data["url"],
      "fixed_bug_ids": fixed_bug_ids,
      "known_bug_ids": known_bug_ids,
  }

  # Remove existing entry for this version/url to prevent driver duplicates
  data["drivers"] = [
      d
      for d in data["drivers"]
      if d["url"] != scraped_data["url"]
      and d.get("version") != scraped_data["version"]
  ]
  data["drivers"].insert(0, new_driver_entry)

  with open(JSON_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4, ensure_ascii=False)

  print(f"Successfully updated drivers.json for version {scraped_data['version']}")


if __name__ == "__main__":
  if len(sys.argv) < 2:
    print("Usage: python update_drivers.py <amd_url>")
    sys.exit(1)

  target_url = sys.argv[1]
  driver_info = fetch_amd_release_notes(target_url)
  update_json(driver_info)
