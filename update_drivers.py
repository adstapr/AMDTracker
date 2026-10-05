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
    return (
        text.replace("â„¢", "™")
        .replace("â€“", "-")
        .replace("Â®", "®")
        .replace("\u200b", "")
        .replace("\xa0", " ")
        .strip()
    )

def get_next_id(master_dict, prefix):
    """Finds the next sequential ID like FEAT-001 or BUG-001."""
    if not master_dict:
        return f"{prefix}-001"
    existing_nums = []
    for key in master_dict.keys():
        match = re.search(r"(\d+)", key)
        if match:
            existing_nums.append(int(match.group(1)))
    next_num = max(existing_nums) + 1 if existing_nums else 1
    return f"{prefix}-{next_num:03d}"

def parse_section_bullets(soup, target_keywords, exclude_keywords=None):
    """Precisely extracts bullet points (<li>) under specific headings while avoiding excluded topics."""
    items = []
    if exclude_keywords is None:
        exclude_keywords = []
    
    for element in soup.find_all(["h2", "h3", "h4", "strong", "b"]):
        text = element.get_text(strip=True)
        # Check if header matches target and doesn't contain excluded keywords
        if any(tk.lower() in text.lower() for tk in target_keywords):
            if any(ek.lower() in text.lower() for ek in exclude_keywords):
                continue
                
            container = element.find_parent(["div", "section", "article", "body"])
            if not container:
                container = element
            
            ul = container.find("ul")
            if not ul:
                sibling = element.find_next_sibling()
                while sibling and sibling.name not in ["h2", "h3", "h4", "section"]:
                    if sibling.name == "ul":
                        ul = sibling
                        break
                    nested_ul = sibling.find("ul") if hasattr(sibling, "find") else None
                    if nested_ul:
                        ul = nested_ul
                        break
                    sibling = sibling.find_next_sibling()
            
            if ul:
                for li in ul.find_all("li", recursive=False):
                    cleaned = clean_text(li.get_text())
                    # Skip generic metadata lines
                    if cleaned and len(cleaned) > 3 and "Package Contents" not in cleaned:
                        items.append(cleaned)
                if items:
                    break
    
    # Fallback to paragraph texts if no <ul> was found
    if not items:
        for element in soup.find_all(["h2", "h3", "h4", "strong", "b"]):
            text = element.get_text(strip=True)
            if any(tk.lower() in text.lower() for tk in target_keywords):
                if any(ek.lower() in text.lower() for ek in exclude_keywords):
                    continue
                sibling = element.find_next_sibling()
                while sibling and sibling.name == "p":
                    cleaned = clean_text(sibling.get_text())
                    if cleaned and len(cleaned) > 3:
                        items.append(cleaned)
                    sibling = sibling.find_next_sibling()
                if items:
                    break

    return items

def fetch_amd_release_notes(url):
    print(f"Fetching release notes from: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.amd.com/"
    }

    fixed_texts = []
    known_texts = []
    feature_texts = []
    game_texts = []
    driver_type = "Optional"

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = "utf-8"

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Strict targeting to prevent cross-contamination
            fixed_texts = parse_section_bullets(soup, ["Fixed Issues"], exclude_keywords=["Known", "Highlights"])
            known_texts = parse_section_bullets(soup, ["Known Issues"], exclude_keywords=["Fixed"])
            game_texts = parse_section_bullets(soup, ["Support for", "New Game Support", "Game Support"])
            feature_texts = parse_section_bullets(soup, ["Highlights", "New Features", "What's New"], exclude_keywords=["Fixed", "Known", "Support for"])

            if "Recommended" in soup.get_text():
                driver_type = "Recommended"
        else:
            print(f"Warning: Received HTTP status {response.status_code}. Proceeding with empty lists.")
    except Exception as e:
        print(f"Notice: Could not scrape text due to network restrictions or timeout ({e}).")

    # Extract version from filename/url safely
    filename = url.split("/")[-1].replace(".html", "")
    raw_version_part = filename.replace("RN-RAD-WIN-", "")
    version_match = re.search(r"(\d+-\d+-\d+)", raw_version_part)
    if version_match:
        version = version_match.group(1).replace("-", ".")
    else:
        version = raw_version_part.replace("-", ".") if raw_version_part else "26.0.0"

    return {
        "version": version,
        "type": driver_type,
        "url": url,
        "fixed_texts": fixed_texts,
        "known_texts": known_texts,
        "feature_texts": feature_texts,
        "game_texts": game_texts,
    }

def update_json(scraped_data):
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    data.setdefault("drivers", [])
    master_bugs = data.setdefault("master_bugs", {})
    master_features = data.setdefault("master_features", {})
    master_games = data.setdefault("master_games", {})

    def process_list(text_list, master_dict, prefix):
        ids = []
        for text in text_list:
            existing_id = next(
                (k for k, v in master_dict.items() if clean_text(v) == clean_text(text)),
                None,
            )
            if existing_id:
                ids.append(existing_id)
            else:
                new_id = get_next_id(master_dict, prefix)
                master_dict[new_id] = text
                ids.append(new_id)
        return ids

    fixed_bug_ids = process_list(scraped_data["fixed_texts"], master_bugs, "BUG")
    known_bug_ids = process_list(scraped_data["known_texts"], master_bugs, "BUG")
    feature_ids = process_list(scraped_data["feature_texts"], master_features, "FEAT")
    game_ids = process_list(scraped_data["game_texts"], master_games, "GAME")

    new_driver_entry = {
        "version": scraped_data["version"],
        "type": scraped_data["type"],
        "url": scraped_data["url"],
        "fixed_bug_ids": fixed_bug_ids,
        "known_bug_ids": known_bug_ids,
        "feature_ids": feature_ids,
        "game_ids": game_ids,
    }

    data["drivers"] = [
        d for d in data["drivers"]
        if d.get("url") != scraped_data["url"] and d.get("version") != scraped_data["version"]
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
