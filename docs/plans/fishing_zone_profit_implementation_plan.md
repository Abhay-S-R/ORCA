# Fishing Zone Page: Profit Feature, Full Implementation Plan

This plan covers everything we discussed: fish per zone, approximate market price, profit per trip, home port filtering, vessel type effect, and a fully visual, read-only page. It contains no code. It tells you what to build, in which order, and with which data.

---

## 1. Goal

On the **Fishing Zone page**, a logged-in user should see:

1. Only the fishing zones near their **home port** (home port Kochi shows the zones of Kerala).
2. The **fish they can catch** in each zone.
3. The **approximate profit per trip** for their **vessel type**.
4. A **green / orange / red profit label** on each zone, so the best zones stand out at a glance.

The page is **read-only and visual**. The user types nothing. Two values that are already saved in the app drive everything:

- **Home port** (chosen at login)
- **Vessel type** (Small fishing boat, Mechanized trawler, Cargo vessel)

All of this appears **only on the Fishing Zone page**. No other page shows profit numbers or profit colours.

---

## 2. Rules for the feature

| Rule | Meaning |
|---|---|
| Read-only | No input boxes, sliders or forms on this page |
| Approximate | Every money value is shown as a range with an "approximate" note |
| One page only | Profit data, colours and badges are used by the Fishing Zone page only |
| Pre-calculated | Profit is worked out ahead of time, not live in the browser |
| Honest | Estimated numbers are labelled as estimates |

---

## 3. Data files you have

| File | What it holds | Use it for |
|---|---|---|
| `final_species_with_prices.csv` | Your friend's species list (3,602 species) plus price columns | **Master file for all calculations** |
| `fish_market_prices.csv` | 74 price rows including groups that are not single species (squid, cuttlefish, crabs, prawns, lobsters, and others) | Only for groups with no `aphia_id` |
| `obis_species.csv` | Species observed in the region, with record counts and depth | Evidence that a fish is present in a zone |
| `aquamaps_species.csv` | Predicted presence probability for 38 species | Confidence that a fish is present in a zone |
| `cmfri_landings.csv` | 2024 all-India landings in tonnes for 71 commercial groups | Relative importance of each fish when estimating catch |
| `species_pipeline_report.json` | Summary of how the species list was built | Reference only |

**Decision: keep one master price table.** Both price files hold the same prices. Choose `final_species_with_prices.csv` as the master and make every price edit there, so the two files never disagree. Use `fish_market_prices.csv` only to look up the groups that have no `aphia_id`.

### Important facts about this data

- Only **54 of the 3,602 species** have a price. The rest are mostly reef and survey species that are not sold in markets. They are **ignored for profit** but can still be listed as "also found here".
- Prices are **estimates**, not official figures. They must be checked against the NFDB Fish Market Price Information System (website: **fmpisnfdb.in**, weekly reports, Kerala landing centre table) before launch.
- CMFRI tonnes are **all-India totals**, not per zone and not per state.
- Two group labels are garbled in the source ("MACKERELS Black pomfret" and "CARANGIDS Threadfins"). They were treated as black pomfret and threadfins and marked Low confidence.

---

## 4. Data you need to store

Think of these as six small tables. Your app may keep them as files or database tables, and the shape is the same either way.

### 4.1 Ports
| Field | Example |
|---|---|
| Port ID | kochi |
| Port name | Kochi |
| State | Kerala |
| Latitude, longitude | 9.96, 76.26 |

### 4.2 Fishing zones
| Field | Example |
|---|---|
| Zone ID | kerala-z1 |
| Zone name | Kochi Offshore |
| State | Kerala |
| Centre point or boundary | latitude, longitude, or a polygon |
| Zone type | nearshore / offshore / deep sea |

### 4.3 Zone to species list
For every zone, the species found there. Build it by checking which species fall inside the zone boundary, using the OBIS and AquaMaps data you already have. Keep these fields per row:

| Field | Purpose |
|---|---|
| Zone ID | Which zone |
| Species ID (`aphia_id`) | Link to the master file |
| Presence confidence | From AquaMaps probability and OBIS record count |
| Catch share | Calculated in section 5 |

### 4.4 Species prices
This is `final_species_with_prices.csv`. The fields you use are:
`aphia_id`, `scientific_name`, `common_name`, `price_low_inr_per_kg`, `price_high_inr_per_kg`, `price_mid_inr_per_kg`, `cmfri_tonnes`, `has_price`, `price_confidence`.

### 4.5 Distances (pre-stored)
For every port and every zone in the same region, store the **sea distance in km** ahead of time. This removes any live distance calculation. A straight-line distance is acceptable for a first version, and you can refine it later.

### 4.6 Vessel profiles and global assumptions
All the numbers that drive cost and catch live in **one table**, so you can change them in one place.

| Item | Small fishing boat | Mechanized trawler | Cargo vessel |
|---|---|---|---|
| Fuel use (litres per km) | 0.5 | 3.0 | 10.0 |
| Fixed cost per trip (crew, ice, food, port fees) | ₹6,000 | ₹25,000 | Not applicable |
| Base catch per trip, all fish together | 250 kg | 750 kg (3× small boat) | None |
| Fishing profit shown? | Yes | Yes | No |

Global assumptions: **diesel price ₹95 per litre**, **profit range of plus or minus 15%**.

These are starting values. My earlier suggestion of ₹4,000 fixed cost for a small boat is low if crew wages are included, which is why this plan uses ₹6,000. Replace every number here with figures you trust, for example from local fishermen or Kerala fisheries department sources.

---

## 5. How catch per trip is estimated

You do not have catch-per-trip data for each zone. The practical method is a **share-based estimate**:

1. For a zone, list the species found there that have a price (`has_price` is true).
2. If there are many, keep the **top 8** by CMFRI tonnes, to avoid noise.
3. Work out each fish's **share**: its CMFRI tonnes divided by the total tonnes of all fish kept for that zone.
4. Multiply the vessel's **base catch per trip** by each share. This gives the estimated kg of each fish.

**Why this works:** fish that India lands in large quantities (sardine, mackerel, ribbonfish) get a bigger share than rare high-value fish (seer, pomfret), which matches reality at a broad level.

**What it cannot do:** it does not know that one zone is richer than another. All zones with the same species mix get the same catch. If you later get real zone-level catch data (from CMFRI, state fisheries department or fisher surveys), replace this step with it. Nothing else in the plan changes.

---

## 6. How profit is calculated

Do these steps for every **home port, zone and vessel type** combination, in this order:

1. **Estimated kg of each fish** = vessel base catch × that fish's share (section 5).
2. **Income of each fish** = estimated kg × price. Do this once with the low price and once with the high price.
3. **Total income** = sum of the income of all fish in the zone.
4. **Fuel cost** = distance from port to zone × 2 (round trip) × vessel litres per km × diesel price.
5. **Total cost** = fuel cost + the vessel's fixed cost.
6. **Profit** = total income − total cost.
7. **Margin** = profit ÷ total income, as a percentage.
8. **Profit range** = the profit calculated with the low prices up to the profit calculated with the high prices. Round both to the nearest ₹500.

Show the **range** on screen, not a single number. Use the mid price only for sorting and for the margin.

### Worked example
Zone: *Kochi Offshore*, 60 km from Kochi. Fish kept: oil sardine, Indian mackerel, ribbonfish, threadfin breams, yellowfin tuna. Mid prices used: ₹105, ₹185, ₹150, ₹150, ₹225 per kg.

| Fish | Share | Small boat kg (250 kg trip) | Small boat income |
|---|---|---|---|
| Oil sardine | 26.5% | 66 | ₹6,958 |
| Indian mackerel | 28.9% | 72 | ₹13,363 |
| Ribbonfish | 25.2% | 63 | ₹9,449 |
| Threadfin breams | 16.6% | 41 | ₹6,220 |
| Yellowfin tuna | 2.8% | 7 | ₹1,583 |

| | Small fishing boat | Mechanized trawler |
|---|---|---|
| Total income | about ₹37,600 | about ₹112,700 (3× the catch) |
| Fuel (120 km round trip) | ₹5,700 | ₹34,200 |
| Fixed cost | ₹6,000 | ₹25,000 |
| Total cost | ₹11,700 | ₹59,200 |
| **Profit (mid prices)** | **about ₹25,900** | **about ₹53,500** |
| Margin | about 69% | about 47.5% |

The trawler earns more rupees but with a lower margin, which is realistic. This is why colours use **margin percentage** and not a fixed rupee amount.

---

## 7. Profit zone colours

Use margin, so the colours stay fair for every vessel type.

| Margin | Label | Colour |
|---|---|---|
| 50% or more | High profit | Green |
| 25% to 50% | Medium profit | Orange |
| Below 25% | Low profit | Red |

In the worked example the small boat zone is green (about 69%) and the trawler zone is orange (about 47.5%).

**Tune the limits after you see real results.** If every zone is green, raise the limits. If every zone is red, lower them. A healthy page shows a mix of all three.

---

## 8. Home port filtering

1. At login, the app already saves the **home port** (for example Kochi).
2. The Fishing Zone page reads the port and finds its **state** (Kerala).
3. It shows **all zones in that state**.
4. Zones are **sorted from highest to lowest profit** for the user's vessel.
5. Optional later step: also include zones from neighbouring states that are within a set distance (for example 200 km) of the port.

If the home port is missing, show a message such as "Set your home port to see nearby zones" and show no profit.

---

## 9. Vessel type behaviour

| Vessel | Behaviour |
|---|---|
| **Small fishing boat** | Normal profit display |
| **Mechanized trawler** | Normal profit display, with higher fuel, higher fixed cost and a larger catch |
| **Cargo vessel** | Does not fish. Hide profit bars, ranges and colours. Show "Profit estimates apply to fishing vessels only." Still show the zones and the species list |
| **Not set** | Use **Small fishing boat** and show "Vessel not set: showing estimates for the small fishing boat." This matches the message already in your app |

When the vessel type changes, these update together: fuel cost, income, profit range, colour label and the order of zones. The best zone for a trawler may not be the best zone for a small boat.

---

## 10. Page design

### 10.1 Layout, top to bottom
1. **Heading**: "Fishing zones near Kochi, Kerala"
2. **Sub line**: "Estimates for: Mechanized trawler"
3. **Map**: only the zones of that state, each coloured green, orange or red; the home port marked with its own icon
4. **Zone cards**, sorted from highest to lowest profit
5. **Footer note**: "Approximate values. Actual catch and prices vary by season and market."

### 10.2 What each zone card shows
- Zone name and distance from the home port
- **Fish icons with names** for each priced species
- A small **bar beside each fish** showing its share of the income
- **Approximate income range** and **approximate profit range** (for example "₹24,000 to ₹28,000 per trip")
- A **profit bar**, a filled bar so zones can be compared quickly
- The **colour label**: High, Medium or Low profit
- A **"Best zone for you"** badge on the first card only
- A collapsed "Also found here" line for species with no price

### 10.3 Page states
| State | What to show |
|---|---|
| Normal | Map and cards as above |
| Cargo vessel | Zones and species, no profit, with the note from section 9 |
| No home port | Message asking to set the home port |
| Zone with no priced species | Show the zone and species, with "Profit not available for this zone" |
| Loading or data error | A simple message, and never an empty page |

### 10.4 Keep colours on this page only
If another page (for example a dashboard) shows zones, show plain names in a neutral style with no profit colours or numbers.

---

## 11. Pre-calculation

Because the page is read-only, work out the numbers **ahead of time** and store the results.

1. For every combination of **home port, zone and vessel type**, run the steps in section 6.
2. Store: income range, cost, profit range, margin, colour label, estimated kg and share for each fish, and the sort rank within the port.
3. The page then only **reads** the row for the user's home port and vessel type and displays it.

Re-run this step whenever prices, vessel numbers, distances or zone species change. It is a quick one-time job each time, not a live calculation.

---

## 12. Edge cases to handle

- Fish with `has_price` false: leave out of profit.
- A zone with fewer than 3 priced species: still show it, but mark it "Limited data".
- Two zones with equal profit: sort by shorter distance first.
- Negative profit: show the Red label and the range as a loss, never hide it.
- Missing distance for a port and zone pair: skip that pair and log it.
- Fish names that differ between data files: always match on `aphia_id`, not on the name.
- Group entries such as squid, crabs and prawns: look them up in `fish_market_prices.csv` by `common_name`.
- Very high or very low prices (sardine can double in a lean season): this is why the profit is shown as a range.

---

## 13. Build order

### Phase 1: Data
1. Confirm `final_species_with_prices.csv` as the master price file.
2. Verify the prices of the top 15 species against the NFDB weekly reports (Kerala landing centre table). Average several weeks.
3. Load ports, zones and the vessel table.
4. Build the zone to species list from your OBIS and AquaMaps data.
5. Add pre-stored distances.

### Phase 2: Calculation
6. Work out the catch shares (section 5).
7. Calculate profit for each port, zone and vessel (section 6).
8. Apply the colour limits (section 7).
9. Check that the results look sensible before building any screens (small boat fuel is always below trawler fuel, margins are between about 0% and 90%, and no zone has an odd outlier).

### Phase 3: Page
10. Home port filter and vessel link.
11. Zone cards with fish icons and bars.
12. Map colouring and the home port icon.
13. "Best zone" badge and sorting.

### Phase 4: Edge cases and polish
14. Cargo vessel, no vessel, no home port and no price states.
15. Footer note and "approximate" wording.
16. Make sure no profit visuals leak onto other pages.

---

## 14. Testing checklist

| Test | Expected result |
|---|---|
| Kochi + Small boat | Only Kerala zones, sorted by profit, small-boat numbers |
| Kochi + Trawler | Same zones, higher rupee profit, lower margin, order may change |
| Kochi + Cargo vessel | Zones and species only, no profit, with the note |
| Another port (for example Mangaluru) | Karnataka zones |
| Vessel not set | Defaults to Small fishing boat, with the message |
| Home port not set | Prompt to set the home port |
| Zone with no priced fish | Zone shown, "Profit not available" |
| Another page that lists zones | No profit colours or numbers |
| Change a price in the master file, re-run the calculation | Profit and colour update on the page |

---

## 15. Honesty and disclaimers

- Prices come from **estimates** until checked against the official NFDB reports.
- Catch per trip is a **model assumption** based on national landing shares, not a measured value for each zone.
- Fuel and fixed costs are **assumed values**, not measured values.
- Show ranges, say "approximate", and never present the profit as a guarantee. Fishermen may make decisions based on this page, so avoid language like "you will earn".

---

## 16. Maintenance

| Task | How often |
|---|---|
| Refresh prices from the NFDB weekly reports | Every 2 to 3 months |
| Review diesel price | When it changes noticeably |
| Review vessel fuel, fixed cost and catch numbers | Twice a year, with input from fishermen |
| Re-run pre-calculation | After any change above |
| Re-check the colour limits | After each refresh |

Later improvements, once the base works: a **season filter** (many species run only in some months), real zone-level catch data, and neighbouring-state zones.

---

## 17. Decisions you need to make

1. **Diesel price, fuel use and fixed costs** for each vessel type, using values you trust.
2. **Top-N species per zone** (this plan uses 8).
3. **Colour limits** (this plan uses 50% and 25%).
4. **Distance method**: straight-line for now, or true sea routes.
5. **Master price file**: this plan uses `final_species_with_prices.csv`.
6. Whether to include **neighbouring-state zones** in the first version.

---

## Appendix: key columns in `final_species_with_prices.csv`

| Column | Meaning |
|---|---|
| `aphia_id` | Unique species ID, the link key |
| `scientific_name`, `common_name` | Names |
| `family`, `order` | Taxonomy |
| `in_obis`, `in_aquamaps`, `in_cmfri` | Which sources include the species |
| `obis_records` | Number of observations (presence evidence) |
| `aquamaps_prob` | Predicted presence probability |
| `cmfri_tonnes` | 2024 all-India landings (used for catch share) |
| `confidence`, `confidence_rationale` | How well the species is validated |
| `price_low_inr_per_kg`, `price_high_inr_per_kg`, `price_mid_inr_per_kg` | Approximate landing price range |
| `category` | Fish type group |
| `price_confidence` | Confidence in the price estimate |
| `has_price` | True only if the fish should count in profit |
