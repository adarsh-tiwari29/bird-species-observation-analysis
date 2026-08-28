# Bird Species Observation Analysis

**Live Dashboard:** [View on Streamlit Cloud](https://bird-observation-analysis.streamlit.app/)

## Project Overview

A complete data analysis pipeline focused on Environmental Studies and Biodiversity Conservation. The project analyzes the distribution, behavior, and diversity of bird species across two distinct ecosystems: **Forest** and **Grassland**.

Using observational data from 11 administrative units, it examines how terrain, climate, and environmental conditions influence avian populations. The findings support wildlife conservation, sustainable land management, and eco-tourism planning.

## Tech Stack

| Layer | Tools |
|---|---|
| Data cleaning and engineering | Python, Pandas, OpenPyXL |
| Database | SQLite |
| Exploratory analysis | Jupyter Notebook, Matplotlib, Seaborn |
| Dashboard | Streamlit, Plotly |

## Key Highlights

### 1. Data Wrangling
- Consolidated **22 Excel sheets** across two source files (Forest and Grassland).
- Resolved schema inconsistencies such as mismatched column names (`TaxonCode` vs `NPSTaxonCode`) and missing fields.
- Standardized everything into a single unified master dataset.

### 2. Database Integration
- Designed a relational schema to store the cleaned master dataset in SQLite.
- Wrote SQL queries for efficient retrieval by the dashboard layer.

### 3. Exploratory Data Analysis
- **Temporal and spatial analysis:** biodiversity hotspots, seasonal sightings, and observation time windows.
- **Environmental correlation:** impact of temperature, humidity, wind, and sky conditions on bird activity.
- **Species and behavioral analysis:** male-to-female ratios, identification method (singing vs calling), and observer distance trends.

### 4. Conservation Insights
- Flagged at-risk species using `PIF_Watchlist_Status` to prioritize regional stewardship and targeted conservation efforts.

## Project Structure

```text
Bird Species Observation Analysis/
├── app.py                                    # Streamlit dashboard application
├── Bird_Monitoring_Data_FOREST.xlsx          # Raw forest ecosystem data
├── Bird_Monitoring_Data_GRASSLAND.xlsx       # Raw grassland ecosystem data
├── Bird_Observation_Cleaned.csv              # Unified cleaned master dataset
├── Bird_Plot_Level_Summary.csv               # Plot-level aggregated summary
├── bird_observations.db                      # SQLite database
├── Bird_Species_Observation_Analysis_EDA.ipynb   # Cleaning, merging and EDA notebook
├── Bird Species Observation Analysis.pdf     # Project documentation and findings
├── requirements.txt                          # Python dependencies
└── README.md
```

## How to Run

1. Clone the repository:
   ```bash
   git clone https://github.com/adarsh-tiwari29/bird-species-observation-analysis
   cd "Bird Species Observation Analysis"
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the notebook to regenerate the cleaned dataset and database (optional, outputs are already included):
   ```bash
   jupyter notebook Bird_Species_Observation_Analysis_EDA.ipynb
   ```

4. Launch the dashboard:
   ```bash
   streamlit run app.py
   ```

   Or use the hosted version: [`<your-streamlit-app-url>`](https://bird-observation-analysis.streamlit.app/)

## Data Sources

- `Bird_Monitoring_Data_FOREST.xlsx` — forest ecosystem observations
- `Bird_Monitoring_Data_GRASSLAND.xlsx` — grassland ecosystem observations

Both files contain multiple sheets, one per administrative unit, merged during preprocessing.
