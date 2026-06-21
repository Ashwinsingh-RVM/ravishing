# HoReCa Data Dictionary

**Sheet**: `12YHTCeJxholgigzmGuf2GtTGsTREiS-EZj4Fod8B5x8` (Tab: Sheet1)
**Records**: ~15,675 enriched HoReCa entities across Goa
**Total Columns**: 65 (A–BM)
**Last Updated**: 2026-02-23

---

## Section 1: Google Places — Core Identity (A–F)

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| A | Place ID | String | Google Places unique identifier (e.g., `ChIJ...`) |
| B | Name | String | Business name |
| C | Types | String | All Google Places types (comma-separated) |
| D | Primary Type | String | Primary Google Places type (e.g., `restaurant`, `bar`, `hotel`) |
| E | Street | String | Street address |
| F | Locality | String | Locality / neighborhood |

## Section 2: Google Places — Location (G–L)

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| G | City | String | City name (e.g., Panaji, Margao, Vasco da Gama) |
| H | State | String | State (always `Goa`) |
| I | Pincode | String | 6-digit PIN code |
| J | Full Address | String | Complete formatted address |
| K | Latitude | Float | GPS latitude |
| L | Longitude | Float | GPS longitude |

## Section 3: Google Places — Contact & Web (M–P)

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| M | Google Maps URL | URL | Direct Google Maps link |
| N | Phone | String | Local phone number |
| O | International Phone | String | Phone in international format (+91...) |
| P | Website | URL | Business website |

## Section 4: Google Places — Operations (Q–S)

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| Q | Opening Hours | String | Opening hours text (multi-line) |
| R | Currently Open | Boolean | Whether open at time of data pull |
| S | Price Level | Integer | Google price level (0–4, where 4 = most expensive) |

## Section 5: Google Places — Reviews (T–U)

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| T | Rating | Float | Google rating (1.0–5.0) |
| U | Total Ratings | Integer | Number of Google reviews |

## Section 6: Google Places — Attributes (V–W)

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| V | Serves Beer | Boolean | Google Places beer attribute |
| W | Serves Wine | Boolean | Google Places wine attribute |

## Section 7: Google Places — Extended Attributes (X–AH)

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| X | Serves Breakfast | Boolean | Serves breakfast |
| Y | Serves Brunch | Boolean | Serves brunch |
| Z | Serves Lunch | Boolean | Serves lunch |
| AA | Serves Dinner | Boolean | Serves dinner |
| AB | Serves Vegetarian | Boolean | Vegetarian food available |
| AC | Dine In | Boolean | Dine-in seating available |
| AD | Takeout | Boolean | Takeout available |
| AE | Delivery | Boolean | Delivery service available |
| AF | Reservable | Boolean | Accepts reservations |
| AG | Wheelchair Accessible | Boolean | Wheelchair accessible entrance |
| AH | Good for Children | Boolean | Family-friendly |

## Section 8: Enrichment — Classification (AI–AL)

These columns are computed by the HoReCa enrichment pipeline (`segment.py`).

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| AI | HoReCa_Type | Enum | Classification: `Hotel`, `Restaurant`, `Cafe`, `Bar`, `Other` |
| AJ | Alcohol_Signal | Enum | `Yes` (serves alcohol), `No`, `Unknown` — derived from beer/wine attributes, type, name |
| AK | Size_Tier | Enum | `Large`, `Medium`, `Small` — based on review count and rating |
| AL | Contactability | Enum | `High` (phone + website), `Medium` (phone only), `Low` (neither) |

## Section 9: Enrichment — Geography & Scoring (AM–AO)

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| AM | Area_Zone | String | Geographic area zone label |
| AN | Priority_Score | Float | Composite score (0–100) combining size, contactability, alcohol, rating |
| AO | Priority_Rank | Integer | Rank by priority score (1 = highest priority) |

## Section 10: Enrichment — Additional Scores (AP–AT)

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| AP | Normalized_Rating | Float | Rating normalized to 0–1 scale |
| AQ | Review_Score | Float | Review volume score (log-scaled) |
| AR | Size_Score | Float | Combined size metric |
| AS | Contact_Score | Float | Contactability numeric score |
| AT | Alcohol_Score | Float | Alcohol signal numeric score |

## Section 11: H3 Hex — Meso Zone ID (AU)

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| AU | h3_res7 | String | H3 hexagonal index at resolution 7 (~5 km² meso zone) |

## Section 12: Meso Zone Analytics (AV–BA)

Meso zones are ~5 km² hexagonal areas (H3 resolution 7). Used for geographic clustering and priority ranking.

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| AV | Zone_ID | String | Meso zone identifier (same as h3_res7) |
| AW | Zone_Name | String | Human-readable zone label (e.g., `Panaji Central`) |
| AX | Zone_HoReCa_Count | Integer | Total HoReCa entities in this zone |
| AY | Zone_Density | Float | Entities per km² in this zone |
| AZ | Zone_Quadrant | String | Priority quadrant: `High Density-High Quality`, `High Density-Low Quality`, `Low Density-High Quality`, `Low Density-Low Quality` |
| BA | Zone_Priority_Rank | Integer | Zone rank (1 = highest priority zone for outreach) |

## Section 13: CRM — Outreach Tracking (BB–BM)

These columns are populated by the ground team via the CRM interface. Initially empty for all records.

| Col | Header | Type | Description |
|-----|--------|------|-------------|
| BB | Outreach_Status | Enum | Current outreach stage. Values: `Waiting for Details`, `Communication`, `Meeting Aligned`, `Meeting Done`, `Mail Sent`, `Onboarded` |
| BC | Owner_Name | String | Business owner's name |
| BD | Owner_Number | Phone | Business owner's phone number |
| BE | SPOC_Name | String | Single Point of Contact name |
| BF | SPOC_Number | Phone | SPOC phone number |
| BG | SPOC_Designation | String | SPOC role/title (e.g., Manager, GM) |
| BH | Outreach_Email | Email | Contact email for outreach |
| BI | Bottles_Per_Week | Integer | Estimated weekly bottle volume |
| BJ | Outreach_Notes | Text | Timestamped notes. Format: `[YYYY-MM-DD HH:MM\|author] note\n---\n` (newest first, appended) |
| BK | Follow_Up_Date | Date | Next follow-up date (YYYY-MM-DD) |
| BL | Last_Updated | DateTime | ISO timestamp of last CRM update |
| BM | Updated_By | String | Name of person who last updated the record |

---

## Outreach Status Funnel

```
Waiting for Details → Communication → Meeting Aligned → Meeting Done → Mail Sent → Onboarded
```

| Status | Meaning |
|--------|---------|
| Waiting for Details | Initial state — entity identified, no contact yet |
| Communication | Initial outreach made (call/visit) |
| Meeting Aligned | Meeting scheduled with decision-maker |
| Meeting Done | Meeting completed, terms discussed |
| Mail Sent | Formal onboarding email/docs sent |
| Onboarded | Entity fully onboarded to DRS program |

---

## Data Sources

| Section | Source |
|---------|--------|
| Cols A–AH | Google Places API (Nearby Search + Place Details) |
| Cols AI–AT | Enrichment pipeline (`segment.py`) — rule-based classification |
| Col AU | H3 library — lat/lng → hex index at resolution 7 |
| Cols AV–BA | Zone analytics (`segment.py`) — H3 clustering + density/quality scoring |
| Cols BB–BM | CRM interface — manual entry by ground team |

---

## Key Metrics

- **Total Records**: ~15,675
- **Meso Zones**: ~243 (H3 res 7, ~5 km²)
- **Alcohol-Serving**: ~3,453
- **Types**: Hotel, Restaurant, Cafe, Bar, Other
- **Coverage**: All of Goa (North + South districts)
