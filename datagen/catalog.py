"""Fictional master data for Kaveri Distributors. Every company, person and number here is
invented for demonstration."""

from __future__ import annotations

import random
import string

from app.rules.normalize import gstin_check_char

# (sku, name, hsn, gst_rate, units_per_carton, carton_kg, price_per_carton, requires_coa)
PRODUCTS = [
    ("SKU-1001", "Herbal Shampoo 180ml", "3305", 18, 48, 9.5, 450, True),
    ("SKU-1002", "Anti-Dandruff Shampoo 340ml", "3305", 18, 24, 9.0, 620, True),
    ("SKU-1003", "Coconut Hair Oil 200ml", "3305", 18, 48, 10.5, 510, True),
    ("SKU-1101", "Neem Bath Soap 100g x4", "3401", 18, 36, 15.2, 780, True),
    ("SKU-1102", "Glycerine Soap 75g", "3401", 18, 144, 11.4, 690, True),
    ("SKU-1201", "Mint Toothpaste 150g", "3306", 18, 72, 11.8, 940, True),
    ("SKU-1301", "Detergent Powder 1kg", "3402", 18, 20, 20.6, 1150, False),
    ("SKU-1302", "Dishwash Liquid 500ml", "3402", 18, 30, 16.0, 870, False),
    ("SKU-1303", "Floor Cleaner 1L", "3402", 18, 12, 13.1, 640, False),
    ("SKU-2001", "Glucose Biscuits 200g", "1905", 18, 60, 12.6, 600, True),
    ("SKU-2002", "Cream Biscuits 120g", "1905", 18, 96, 12.0, 860, True),
    ("SKU-2101", "Instant Noodles 70g", "1902", 18, 96, 7.2, 1050, True),
    ("SKU-2201", "Assam Tea 500g", "0902", 5, 24, 12.8, 3100, True),
    ("SKU-2301", "Sunflower Oil 1L", "1512", 5, 12, 11.5, 1680, True),
    ("SKU-2401", "Tomato Ketchup 500g", "2103", 12, 24, 13.4, 1260, True),
    ("SKU-2501", "Pure Ghee 500ml", "0405", 12, 20, 10.8, 5400, True),
    ("SKU-3001", "Paper Napkins 100s", "4818", 12, 48, 8.4, 720, False),
    ("SKU-3002", "Aluminium Foil 9m", "7607", 18, 50, 6.3, 1450, False),
]

SUPPLIER_NAMES = [
    "Sahyadri Personal Care Pvt Ltd", "Nilgiri Home Products LLP", "Cauvery Foods Pvt Ltd",
    "Malabar Consumer Goods Ltd", "Deccan Hygiene Industries", "Coromandel Snacks Pvt Ltd",
    "Palar Edible Oils Ltd", "Vaigai Beverages Pvt Ltd", "Tungabhadra Detergents Ltd",
    "Godavari Packaged Foods", "Krishna Dairy Products LLP", "Hampi Paper Mills Pvt Ltd",
    "Thamirabarani Soaps Ltd", "Kodagu Plantations Pvt Ltd", "Bhavani Cleaning Solutions",
    "Sharavathi Foods LLP", "Kaveri Valley Organics", "Pennar Personal Care Ltd",
]

TRANSPORTERS = ["Sri Murugan Roadways", "Velan Logistics", "Southern Cargo Movers", "Annamalai Transport Co"]
STATE_CODES = ["33", "29", "32", "36", "27"]  # TN, KA, KL, TS, MH

BUYER = {"name": "Kaveri Distributors Pvt Ltd (fictional)", "address": "Plot 14, SIPCOT Industrial Park, Hosur, TN",
         "state_code": "33"}


def make_gstin(rng: random.Random, state: str) -> str:
    pan = "".join(rng.choices(string.ascii_uppercase, k=3)) + rng.choice("PCF") + rng.choice(string.ascii_uppercase)
    pan += "".join(rng.choices(string.digits, k=4)) + rng.choice(string.ascii_uppercase)
    first14 = f"{state}{pan}1Z"
    return first14 + gstin_check_char(first14)


def vehicle(rng: random.Random) -> str:
    return f"{rng.choice(['TN', 'KA', 'KL'])}{rng.randint(1, 99):02d} {rng.choice(string.ascii_uppercase)}" \
           f"{rng.choice(string.ascii_uppercase)} {rng.randint(1000, 9999)}"
