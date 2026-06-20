from dateutil import parser
import re
from datetime import timedelta

# --- Shared Parsers ---
RO_MONTHS = {
    'ianuarie': 1, 'februarie': 2, 'martie': 3, 'aprilie': 4,
    'mai': 5, 'iunie': 6, 'iulie': 7, 'august': 8,
    'septembrie': 9, 'octombrie': 10, 'noiembrie': 11, 'decembrie': 12
}

def parse_romanian_date(date_text):
    if not date_text:
        return None
    # We make the time part (\d{2}:\d{2}) optional using (?:...)?
    match = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})(?:\s+.*?(\d{2}:\d{2}))?', date_text, re.IGNORECASE)
    if match:
        day, month_str, year, time_str = match.groups()
        month_num = RO_MONTHS.get(month_str.lower(), 1)
        
        # Default to 00:00 if no time is present on the page
        if not time_str:
            time_str = "00:00"
            
        standard_date_str = f"{year}-{month_num:02d}-{day.zfill(2)} {time_str}"
        return parser.parse(standard_date_str)
    return None

def parse_iso_date(date_text):
    if not date_text:
        return None
    try:
        return parser.parse(date_text)
    except Exception:
        return None

def is_valid_desteptarea_link(url):
    if not url.startswith("https://www.desteptarea.ro/"):
        return False
    path = url.replace("https://www.desteptarea.ro/", "").strip("/")
    if re.fullmatch(r'\d+(-\d+)?', path) or "/" in path:
        return False
    return True

def parse_factual_json_date(text):
    if not text:
        return None
    if '"datePublished"' in text:
        match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', text)
        if match:
            return parser.parse(match.group(1))
    return parse_iso_date(text)

def parse_pressone_date(date_text):
    if not date_text:
        return None
    
    date_text = date_text.strip()

    match = re.search(r'(\d{1,2})\s*[/\.\-\s]\s*(\d{1,2})\s*[/\.\-\s]\s*(\d{4})', date_text)
    if match:
        day, month, year = match.groups()
        return parser.parse(f"{year}-{month.zfill(2)}-{day.zfill(2)}")
        
    # Fallback: Romanian text dates
    try:
        return parse_romanian_date(date_text)
    except Exception:
        pass
        
    return None

def parse_agerpres_date(date_text):
    if not date_text:
        return None
    
    # Clean the string by removing "Data: " and extra spaces
    clean_text = date_text.replace("Data:", "").strip()
    
    try:
        # Agerpres uses a very clean DD-MM-YYYY HH:MM format
        return parser.parse(clean_text, dayfirst=True)
    except Exception:
        return None

# --- Rules Dictionary ---
RULES = {
    1: {
        "name": "Ziare",
        "discover_type": "html",
        "archive_base_url": "https://ziare.com/arhiva/{date}",
        "discover_xpath": '//div[contains(@class, "title__article")]/a/@href',
        "worker_xpaths": {
            "title": '//h1/text()',
            "content": '//div[contains(@class, "news__content") and contains(@class, "descriere_main")]//p//text()',
            "author": '//div[contains(@class, "news__author")]//a/text()',
            "date": '//div[contains(@class, "news__publish")]/text()'
        },
        "date_parser": parse_romanian_date,
        "link_validator": lambda url: not any(noise in url.lower() for noise in [
            'bancuri', 'bancul-zilei', 'horoscop', 'zodiac', 
            'retete', 'culinar', 'meteo', 'sport', 'cancan', 'monden'
        ])
    },
    2: {
        "name": "Desteptarea",
        "discover_type": "html",
        "archive_base_url": "https://www.desteptarea.ro/{year}/{month}/{day}/", 
        "discover_xpath": '//h3[contains(@class, "entry-title")]/a/@href',
        "worker_xpaths": {
            "title": '//h1/text()',
            "content": '//div[contains(@class, "tdb_single_content")]//p//text()',
            "author": '//div[contains(@class, "tdb_single_author")]//a/text()',
            "date": '//time[contains(@class, "entry-date")]/@datetime'
        },
        "date_parser": parse_iso_date,
        "link_validator": is_valid_desteptarea_link
    },
    3: {
        "name": "Factual",
        "discover_type": "json_api", 
        "archive_base_url": [
            "https://www.factual.ro/wp-json/wp/v2/posts?after={date}T00:00:00&before={next_date}T00:00:00&per_page=100",
            "https://www.factual.ro/wp-json/wp/v2/declaratii?after={date}T00:00:00&before={next_date}T00:00:00&per_page=100",
            "https://www.factual.ro/wp-json/wp/v2/dezinformari-rs?after={date}T00:00:00&before={next_date}T00:00:00&per_page=100"
        ],
        "discover_xpath": None, 
        "worker_xpaths": {
            "title": '//h1[contains(@class, "ultp-builder-title")]/text()',
            "content": '//div[contains(@class, "ultp-builder-container")]//p//text()',
            "author": None,
            "date": '//script[contains(text(), "datePublished")]/text()'
        },
        "date_parser": parse_factual_json_date,
        "link_validator": lambda url: True 
    },
    4: {
        "name": "PressOne",
        "discover_type": "category_crawl", 
        "base_categories": [
            "https://pressone.ro/categorie/stiri",
            "https://pressone.ro/categorie/opinii",
            "https://pressone.ro/categorie/mediu",
            "https://pressone.ro/categorie/orase",
            "https://pressone.ro/categorie/dezinformare",
            "https://pressone.ro/categorie/international",
            "https://pressone.ro/categorie/tineri",
            "https://pressone.ro/categorie/projectf",
            "https://pressone.ro/categorie/istorie",
            "https://pressone.ro/categorie/viitorul-tech"
        ],
        "item_xpath": '//div[contains(@class, "col-12")]', 
        "link_xpath": './/a[contains(@class, "text-black")]/@href',
        "worker_xpaths": {
            "title": '//h1//text()', 
            "content": '//article//p//text()', 
            "author": '//div[contains(@class, "author-sm")]//text()', 
            "date": '//div[contains(@class, "justify-content-between") and contains(@class, "align-baseline")]/p/text() | //p[contains(@class, "date-container")]//text()'
        },
        "date_parser": parse_pressone_date,
        "link_validator": lambda url: not any(noise in url.lower() for noise in [
            'bancuri', 'bancul-zilei', 'horoscop', 'zodiac', 
            'retete', 'culinar', 'meteo', 'sport', 'cancan', 'monden'
        ])
    },
    5: {
        "name": "Agerpres",
        "discover_type": "category_crawl", 
        "base_categories": [
            "https://agerpres.ro/politic",
            "https://agerpres.ro/social",
            "https://agerpres.ro/economic",
            "https://agerpres.ro/justitie",
            "https://agerpres.ro/cultura-media",
            "https://agerpres.ro/educatie-stiinta",
            "https://agerpres.ro/sanatate",
            "https://agerpres.ro/documentare",
            "https://agerpres.ro/politic-extern",
            "https://agerpres.ro/economic-extern",
            "https://agerpres.ro/social-extern",
            "https://agerpres.ro/stiinta",
            "https://agerpres.ro/zigzag",
            "https://agerpres.ro/romania-in-lume",
            "https://agerpres.ro/cultura",
            "https://agerpres.ro/special/orient",
            "https://agerpres.ro/special/reportaj",
            "https://agerpres.ro/special/interviuagerpres"
        ],
        "item_xpath": '//div[contains(@class, "card") and contains(@class, "bg-transparent")]', 
        "link_xpath": './/h3/a/@href',
        "worker_xpaths": {
            "title": '//h2//text()', 
            "content": '//div[contains(@class, "article")]//p//text()', 
            "author": None, 
            "date": '//li[contains(@class, "article-date")]//text()'
        },
        "date_parser": parse_agerpres_date,
        "link_validator": lambda url: True
    },
    6: {
        "name": "Veridica",
        "discover_type": "category_crawl", 
        "pagination_style": "query",
        "base_categories": [
            "https://www.veridica.ro/stiri/romania",
            "https://www.veridica.ro/stiri/international",
            "https://www.veridica.ro/stiri/eticheta/razboi-in-ucraina",
            "https://www.veridica.ro/opinii",
            "https://www.veridica.ro/interviuri",
            "https://www.veridica.ro/2024-anul-marii-resetari",
            "https://www.veridica.ro/investigatie",
            "https://www.veridica.ro/fake-news-dezinformare-propaganda",
            "https://www.veridica.ro/teoria-conspiratiei",
            "https://www.veridica.ro/monitor-fake-news",
            "https://www.veridica.ro/presa-rusa-independenta",
            "https://www.veridica.ro/presa-rusa-pro-kremlin",
            "https://www.veridica.ro/russkii-mir"
        ],
        "item_xpath": '//div[contains(@class, "card") and contains(@class, "border-0")]', 
        "link_xpath": './/h5[contains(@class, "card-title")]/a/@href',
        "worker_xpaths": {
            "title": '//h1//text()', 
            "content": '//div[contains(@class, "page-content")]//p//text()', 
            "author": '//a[contains(@href, "/autori/")]//strong//text()', 
            "date": '//time/@datetime' 
        },
        "date_parser": parse_iso_date,
        "link_validator": lambda url: True
    },
    7: {
        "name": "Gazeta de Sud",
        "discover_type": "category_crawl", 
        "pagination_style": "path_page",
        "base_categories": [
            "https://www.gds.ro/Local",
            "https://www.gds.ro/Sanatate",
            "https://www.gds.ro/Educatie",
            "https://www.gds.ro/Bani-afaceri",
            "https://www.gds.ro/politica"
        ],
        "item_xpath": '//div[contains(@class, "td-pb-span8")]//div[contains(@class, "td-module-container")]',
        "link_xpath": './/h3[contains(@class, "entry-title")]/a/@href',
        "worker_xpaths": {
            "title": '//h1[contains(@class, "tdb-title-text")]//text() | //h1[contains(@class, "entry-title")]//text()', 
            "content": '//div[contains(@class, "tdb-block-inner")]//p//text() | //div[contains(@class, "td-post-content")]//p//text()', 
            "author": '//div[contains(@class, "tdb-author-name")]//text() | //span[contains(@class, "td-post-author-name")]//text()', 
            "date": '//meta[@property="article:published_time"]/@content | //div[contains(@class, "tdb_single_date")]//time/@datetime'
        },
        "date_parser": parse_iso_date,
        "link_validator": lambda url: url.startswith("https://www.gds.ro/")
    },
    8: {
        "name": "Argesul Online",
        "discover_type": "category_crawl", 
        "pagination_style": "path_page",
        "base_categories": [
            "https://argesulonline.ro/category/actualitate",
            "https://argesulonline.ro/category/cultura",
            "https://argesulonline.ro/category/national",
            "https://argesulonline.ro/category/international"
        ],
        "item_xpath": '//div[contains(@class, "tdb_module_loop") or contains(@class, "td-module-container")]',
        # Using * instead of h3 because Argesul uses h2 for their titles in the feed
        "link_xpath": './/*[contains(@class, "entry-title")]/a/@href',
        "worker_xpaths": {
            "title": '//h1[contains(@class, "tdb-title-text")]//text() | //h1[contains(@class, "entry-title")]//text()', 
            "content": '//div[contains(@class, "tdb-block-inner")]//p//text() | //div[contains(@class, "td-post-content")]//p//text()', 
            "author": '//div[contains(@class, "tdb-author-name")]//text() | //span[contains(@class, "td-post-author-name")]//text()', 
            # SEO Meta tag first, fallback to the datetime attribute
            "date": '//meta[@property="article:published_time"]/@content | //time[contains(@class, "entry-date")]/@datetime'
        },
        "date_parser": parse_iso_date,
        "link_validator": lambda url: url.startswith("https://argesulonline.ro/")
    },
    9: {
        "name": "Buletin de Bucuresti",
        "discover_type": "category_crawl", 
        "pagination_style": "path_page",
        "base_categories": [
            "https://buletin.de/bucuresti/tag/pmb",
            "https://buletin.de/bucuresti/tag/ilfov",
            "https://buletin.de/bucuresti/tag/sector-1",
            "https://buletin.de/bucuresti/tag/sector-2",
            "https://buletin.de/bucuresti/tag/sector-3",
            "https://buletin.de/bucuresti/tag/sector-4",
            "https://buletin.de/bucuresti/tag/sector-5",
            "https://buletin.de/bucuresti/tag/sector-6",
            "https://buletin.de/bucuresti/category/investigatii",
            "https://buletin.de/bucuresti/category/mediu",
            "https://buletin.de/bucuresti/category/interviu",
            "https://buletin.de/bucuresti/category/transport",
            "https://buletin.de/bucuresti/category/cultura",
            "https://buletin.de/bucuresti/category/termo",
            "https://buletin.de/bucuresti/category/reportaj",
            "https://buletin.de/bucuresti/category/editorial"
        ],
        # SCOPING: Only target items inside the main list, ignoring the sidebar
        "item_xpath": '//div[contains(@class, "jl_main_list_cw")]//div[contains(@class, "jl_clist_layout")]', 
        "link_xpath": './/h3[contains(@class, "jl_fe_title")]/a/@href',
        "worker_xpaths": {
            "title": '//h1[contains(@class, "jl_head_title")]//text()', 
            "content": '//div[contains(@class, "post_content_w")]//p//text()', 
            "author": '//span[contains(@class, "jl_post_author_name")]//text()', 
            "date": '//meta[@property="article:published_time"]/@content | //div[contains(@class, "jl_mt_wrap")]//span[contains(@class, "post-date")]//text()'
        },
        "date_parser": parse_pressone_date,
        "link_validator": lambda url: url.startswith("https://buletin.de/bucuresti/")
    },
    10: {
        "name": "Arad24",
        "discover_type": "category_crawl", 
        "pagination_style": "path_page",
        "base_categories": [
            "https://arad24.net/category/administratie",
            "https://arad24.net/category/cronica-neagra",
            "https://arad24.net/category/cultura",
            "https://arad24.net/category/editorial",
            "https://arad24.net/category/soparlita-guresa",
            "https://arad24.net/category/politic",
            "https://arad24.net/category/economic",
            "https://arad24.net/category/eveniment",
            "https://arad24.net/category/punct-fix"
        ],
        "item_xpath": '//div[contains(@class, "td-main-content")]//div[contains(@class, "td_module_")]',
        "link_xpath": './/h3[contains(@class, "entry-title")]/a/@href',
        "worker_xpaths": {
            "title": '//h1[contains(@class, "entry-title")]//text() | //h1[contains(@class, "tdb-title-text")]//text()', 
            "content": '//div[contains(@class, "td-post-content")]//p//text() | //div[contains(@class, "tdb-block-inner")]//p//text()', 
            "author": '//div[contains(@class, "td-post-author-name")]//a//text() | //div[contains(@class, "tdb-author-name")]//text()', 
            "date": '//meta[@property="article:published_time"]/@content | //header[contains(@class, "td-post-title")]//time/@datetime'
        },
        "date_parser": parse_iso_date,
        "link_validator": lambda url: url.startswith("https://arad24.net/")
    },
    11: {
        "name": "Defapt.ro",
        "discover_type": "category_crawl", 
        "pagination_style": "query",
        "base_categories": [
            "https://defapt.ro/investigatii",
            "https://defapt.ro/eveniment",
            "https://defapt.ro/politica",
            "https://defapt.ro/justitie",
            "https://defapt.ro/opinii",
            "https://defapt.ro/international"
        ],
        # SCOPING: Defapt uses <article> tags inside the <main> feed.
        "item_xpath": '//main//article', 
        # The main link wraps the h2 title.
        "link_xpath": './/a[descendant::h2]/@href',
        "worker_xpaths": {
            "title": '//h1//text()', 
            "content": '//div[contains(@class, "content")]//p//text()', 
            "author": '//span[contains(@class, "text-zinc-500")]//text() | //div[contains(@class, "text-zinc-500")]//text()', 
            "date": '//meta[@property="article:published_time"]/@content | //span[contains(@class, "text-zinc-700")]//text()'
        },
        "date_parser": parse_pressone_date,
        "link_validator": lambda url: url.startswith("https://defapt.ro/")
    },
    12: {
        "name": "Monitorul de Botosani",
        "discover_type": "category_crawl", 
        "pagination_style": "path_page", # Uses /page/2/
        "base_categories": [
            "https://www.monitorulbt.ro/category/local",
            "https://www.monitorulbt.ro/category/editorial",
            "https://www.monitorulbt.ro/category/national",
            "https://www.monitorulbt.ro/category/international",
        ],
        # SCOPING: Lock selectors inside the main content column to bypass all sidebars
        "item_xpath": '//div[contains(@class, "td-main-content")]//div[contains(@class, "tdb_module_loop") or contains(@class, "td-module-container")]', 
        "link_xpath": './/h3[contains(@class, "entry-title")]/a/@href',
        "worker_xpaths": {
            "title": '//h1[contains(@class, "entry-title")]//text() | //h1[contains(@class, "tdb-title-text")]//text()', 
            "content": '//div[contains(@class, "td-post-content")]//p//text() | //div[contains(@class, "tdb-block-inner")]//p//text()', 
            "author": '//div[contains(@class, "tdb-author-name")]//text() | //span[contains(@class, "td-post-author-name")]//text()', 
            "date": '//meta[@property="article:published_time"]/@content | //div[contains(@class, "tdb_single_date")]//time/@datetime'
        },
        "date_parser": parse_iso_date, # Relies on the perfect ISO timestamp string
        "link_validator": lambda url: url.startswith("https://www.monitorulbt.ro/")
    }
}