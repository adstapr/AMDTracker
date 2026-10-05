import json
import os
import re
import sys
from bs4 import BeautifulSoup
import requests

JSON_FILE = "drivers.json"

def clean_text(text):
    if not text:
        return ""
    # Strip trailing resolution target notices (e.g., [Resolution targeted for 22.10.3])
    text = re.sub(r'\s*\[?Resolution targeted for [^\]]+\]?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(?Resolution targeted for [^\)]+\)?', '', text, flags=re.IGNORECASE)
    return (
        text.replace("â„¢", "™")
        .replace("â€“", "-")
        .replace("Â®", "®")
        .replace("\u200b", "")
        .replace("\xa0", " ")
        .strip()
    )

def get_next_id(master_dict, prefix):
    if not master_dict:
        return f"{prefix}-001"
    existing_nums = []
    for key in master_dict.keys():
        match = re.search(r"(\d+)", key)
        if match:
            existing_nums.append(int(match.group(1)))
    next_num = max(existing_nums) + 1 if existing_nums else 1
    return f"{prefix}-{next_num:03d}"

def get_main_content(soup):
    # Target main article or content body to avoid footers/navs
    return soup.find(["article", "main"]) or soup.find("div", class_=re.compile(r"content|node|release-notes", re.I)) or soup

def parse_amd_section(soup, keywords):
    items = []
    main_container = get_main_content(soup)
    target_tag = None
    
    for tag in main_container.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "p"]):
        text = tag.get_text(strip=True).rstrip(':').strip()
        if not text:
            continue
        if any(kw.lower() == text.lower() or (len(kw) > 3 and kw.lower() in text.lower()) for kw in keywords):
            if tag.name in ["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"] or len(text) < 50:
                target_tag = tag
                break
            
    if not target_tag:
        return items

    curr = target_tag.find_next_sibling()
    if not curr and target_tag.parent and target_tag.parent.name in ["p", "div", "li"]:
        curr = target_tag.parent.find_next_sibling()

    while curr:
        if curr.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            break
            
        if curr.name in ["ul", "ol"]:
            for li in curr.find_all("li", recursive=False):
                li_copy = BeautifulSoup(str(li), "html.parser")
                for nested in li_copy.find_all(["ul", "ol"]):
                    nested.decompose()
                cleaned = clean_text(li_copy.get_text())
                if cleaned and len(cleaned) > 2 and cleaned not in items:
                    items.append(cleaned)
        elif curr.name == "p":
            cleaned = clean_text(curr.get_text())
            if cleaned and len(cleaned) > 2 and cleaned not in items:
                items.append(cleaned)
        else:
            if hasattr(curr, "find_all"):
                for ul in curr.find_all(["ul", "ol"]):
                    for li in ul.find_all("li", recursive=False):
                        li_copy = BeautifulSoup(str(li), "html.parser")
                        for nested in li_copy.find_all(["ul", "ol"]):
                            nested.decompose()
                        cleaned = clean_text(li_copy.get_text())
                        if cleaned and len(cleaned) > 2 and cleaned not in items:
                            items.append(cleaned)
                for p in curr.find_all("p"):
                    cleaned = clean_text(p.get_text())
                    if cleaned and len(cleaned) > 2 and cleaned not in items:
                        items.append(cleaned)
                        
        curr = curr.find_next_sibling()
        
    return items

def parse_amd_games_section(soup):
    items = []
    keywords = ["support for", "new game support", "game support", "optimized for"]
    main_container = get_main_content(soup)
    
    target_tags = []
    for tag in main_container.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"]):
        text = tag.get_text(strip=True).rstrip(':').strip()
        if any(kw == text.lower() or text.lower().startswith(kw) for kw in keywords):
            target_tags.append(tag)
            
    for target_tag in target_tags:
        curr = target_tag.find_next_sibling()
        if not curr and target_tag.parent:
            curr = target_tag.parent.find_next_sibling()
            
        while curr:
            if curr.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                break
            if curr.name in ["ul", "ol"]:
                for li in curr.find_all("li", recursive=True):
                    li_copy = BeautifulSoup(str(li), "html.parser")
                    for nested in li_copy.find_all(["ul", "ol"]):
                        nested.decompose()
                    cleaned = clean_text(li_copy.get_text())
                    if cleaned and len(cleaned) > 1 and cleaned not in items:
                        items.append(cleaned)
            elif curr.name == "p":
                cleaned = clean_text(curr.get_text())
                if cleaned and cleaned.lower().rstrip(':') not in keywords:
                    if cleaned and len(cleaned) > 1 and cleaned not in items:
                        items.append(cleaned)
            elif hasattr(curr, "find_all"):
                for ul in curr.find_all(["ul", "ol"]):
                    for li in ul.find_all("li", recursive=True):
                        li_copy = BeautifulSoup(str(li), "html.parser")
                        for nested in li_copy.find_all(["ul", "ol"]):
                            nested.decompose()
                        cleaned = clean_text(li_copy.get_text())
                        if cleaned and len(cleaned) > 1 and cleaned not in items:
                            items.append(cleaned)
            curr = curr.find_next_sibling()
            
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
            
            fixed_texts = parse_amd_section(soup, ["Fixed Issues"])
            known_texts = parse_amd_section(soup, ["Known Issues"])
            game_texts = parse_amd_games_section(soup)
            feature_texts = parse_amd_section(soup, ["Highlights", "New Features", "What's New"])
            
            # Strict separation to prevent games from leaking into features
            feature_texts = [
                f for f in feature_texts 
                if not any(g.lower() in f.lower() for g in game_texts) 
                and "support for" not in f.lower()
                and "game support" not in f.lower()
            ]

            if "Recommended" in soup.get_text():
                driver_type = "Recommended"
        else:
            print(f"Warning: Received HTTP status {response.status_code}. Proceeding with empty lists.")
    except Exception as e:
        print(f"Notice: Could not scrape text due to network restrictions or timeout ({e}).")

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
