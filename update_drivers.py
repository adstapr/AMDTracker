import json
import os
import re
import sys
from bs4 import BeautifulSoup
import requests

JSON_FILE = "drivers.json"


def get_next_bug_id(master_bugs):
  """Finds the next sequential bug ID like BUG-022."""
  if not master_bugs:
    return "BUG-001"
  existing_nums = []
  for key in master_bugs.keys():
    match = re.search(r"(\d+)", key)
    if match:
      existing_nums.append(int(match.group(1)))
  next_num = max(existing_nums) + 1 if existing_nums else 1
  return f"BUG-{next_num:03d}"


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
            cleaned = li.get_text().strip()
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
  date_str = ""
  driver_type = "Optional"  # Default assumption

  try:
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
      soup = BeautifulSoup(response.text, "html.parser")

      # Extract Fixed Issues and Known Issues
      fixed_texts = parse_list_items(soup, ["Fixed Issues"])
      known_texts = parse_list_items(soup, ["Known Issues"])

      # Look for release date or type hints on page if available
      page_text = soup.get_text()
      if "Recommended" in page_text:
        driver_type = "Recommended"

  except Exception as e:
    print(f"Notice: Could not scrape text due to network restrictions ({e}).")

  # Extract version from filename (e.g., RN-RAD-WIN-22-11-2.html -> 22.11.2)
  filename = url.split("/")[-1].replace(".html", "")
  raw_version_part = filename.replace("RN-RAD-WIN-", "")
  # Clean up extra tags like -RX7900 or -HOTFIX if present, keeping numbers/dots
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
    with open(JSON_FILE, "r") as f:
      data = json.load(f)
  else:
    data = {"drivers": [], "master_bugs": {}}

  master_bugs = data.setdefault("master_bugs", {})

  # Helper to process text lists into ID references
  def process_bug_list(text_list):
    bug_ids = []
    for text in text_list:
      # Check if this exact bug description already exists in master_bugs to prevent duplicates
      existing_id = next(
          (k for k, v in master_bugs.items() if v == text), None
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

  # Remove existing entry for this version/url if it exists to avoid duplicates
  data["drivers"] = [
      d
      for d in data["drivers"]
      if d["url"] != scraped_data["url"]
      and d.get("version") != scraped_data["version"]
  ]

  # Insert at the top of the list
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
