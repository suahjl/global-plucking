# %%
import pandas as pd
from datetime import date, timedelta
import re
from helper import (
    telsendmsg,
    telsendimg,
    telsendfiles,
    reg_ols,
    fe_reg,
    re_reg,
    gmmiv_reg,
    heatmap,
    pil_img2pdf,
    subplots_linecharts,
)
import statsmodels.tsa.api as smt
from statsmodels.tsa.ar_model import ar_select_order
import localprojections as lp
from tqdm import tqdm
import time
import os
from dotenv import load_dotenv
import ast

time_start = time.time()

# %%
# 0 --- Main settings
load_dotenv()
path_data = "./data/"
path_output = "./output/"
path_ceic = "./ceic/"
tel_config = os.getenv("TEL_CONFIG")
t_start_q = "1991Q1"
t_end_q = "2023Q1"

# %%
# I --- Load data
# Macro
df = pd.read_parquet(path_data + "data_macro_quarterly.parquet")
# UGap
df_ugap = pd.read_parquet(path_output + "plucking_ugap_quarterly.parquet")
# df_ugap["quarter"] = pd.to_datetime(df_ugap["month"]).dt.to_period("q")
# df_ugap = (
#     df_ugap.groupby(["country", "quarter"])[["urate_ceiling", "urate_gap"]]
#     .mean()
#     .reset_index(drop=False)
# )
df_ugap["quarter"] = df_ugap["quarter"].astype("str")
# Expected inflation
df_expcpi = pd.read_parquet(path_data + "data_macro_quarterly_expcpi.parquet")
# Merge
df = df.merge(df_ugap, on=["country", "quarter"], how="outer", validate="one_to_one")
df = df.merge(df_expcpi, on=["country", "quarter"], how="outer", validate="one_to_one")
# Sort
df = df.sort_values(by=["country", "quarter"])
# Load parameter estimates from phillips curve analysis
df_params = pd.read_parquet(
    path_output + "phillipscurve_urate_ugap_params_fe_reer" + ".parquet"
)

# %%
# II --- Pre-analysis wrangling
# Trim countries
countries_asean4 = ["malaysia", "thailand", "indonesia", "philippines"]
countries_asianie = ["singapore", "south_korea", "hong_kong_sar_china_"]
countries_bigemerging = ["india", "mexico", "brazil", "chile"]
countries_adv = [
    "united_states",
    "japan",
    "australia",
    "united_kingdom",
    "germany",
    "france",
    "italy",
]
list_countries_keep = (
    countries_adv + countries_asianie + countries_bigemerging + countries_asean4
)
df = df[df["country"].isin(list_countries_keep)]
# Transform (harmonise with version in PC estimation)
cols_pretransformed = ["rgdp", "m2", "cpi", "corecpi", "maxgepu", "expcpi"]
cols_levels = ["reer", "ber", "brent", "gepu"]
cols_rate = ["stir", "ltir", "urate_ceiling", "urate", "privdebt", "privdebt_bank"]
for col in cols_levels:
    df[col] = 100 * ((df[col] / df.groupby("country")[col].shift(4)) - 1)
for col in cols_rate:
    df[col] = df[col] - df.groupby("country")[col].shift(4)
# Generate lists for charting
nested_list_country_groups = [
    countries_asean4,
    countries_asianie,
    countries_bigemerging,
    countries_adv,
]
nice_group_names_by_country_groups = ["ASEAN-4", "Asian NIEs", "Major EMs", "AEs"]
snakecase_group_names_by_country_groups = ["asean4", "asianie", "bigemerging", "adv"]
rows_by_country_groups = [2, 2, 2, 3]
cols_by_country_groups = [2, 2, 2, 3]

# %%
# III --- Compute dynamic slope + trim data set
df["slope"] = (
    df_params.loc["urate", "Parameter"]
    + df_params.loc["urate_int_urate_gap", "Parameter"] * df["urate_gap"]
)
df["slope_lb"] = (
    df_params.loc["urate", "LowerCI"]
    + df_params.loc["urate_int_urate_gap", "LowerCI"] * df["urate_gap"]
)
df["slope_ub"] = (
    df_params.loc["urate", "UpperCI"]
    + df_params.loc["urate_int_urate_gap", "UpperCI"] * df["urate_gap"]
)
df["zero"] = 0
df = df[["country", "quarter", "slope", "slope_lb", "slope_ub", "zero"]]

# %%
# IV --- Plot
list_file_names = []
for country_groups, snakecase_group_name, nice_group_name, n_rows, n_cols in tqdm(
    zip(
        nested_list_country_groups,
        snakecase_group_names_by_country_groups,
        nice_group_names_by_country_groups,
        rows_by_country_groups,
        cols_by_country_groups,
    )
):
    df_sub = df[df["country"].isin(country_groups)].copy()
    fig = subplots_linecharts(
        data=df_sub,
        col_group="country",
        cols_values=["slope", "slope_lb", "slope_ub", "zero"],
        cols_values_nice=["Slope of the Estimated PC", "Lower Bound", "Upper Bound", "Slope=0"],
        col_time="quarter",
        annot_size=11,
        font_size=11,
        line_colours=["black", "black", "black", "darkgrey"],
        line_dashes=["solid", "dash", "dash", "dot"],
        main_title=("Estimated Phillips Curve Slope" + " in " + nice_group_name),
        maxrows=n_rows,
        maxcols=n_cols,
    )
    file_name = (
        path_output + "phillipscurve_slope_urate_ugap" + "_" + snakecase_group_name
    )
    fig.write_image(file_name + ".png")
    # telsendimg(
    #     conf=tel_config,
    #     path=file_name + ".png",
    #     cap=file_name
    # )
    list_file_names += [file_name]
pdf_file_name = path_output + "phillipscurve_slope_urate_ugap"
pil_img2pdf(list_images=list_file_names, extension="png", pdf_name=pdf_file_name)
telsendfiles(conf=tel_config, path=pdf_file_name + ".pdf", cap=pdf_file_name)


# %%
# X --- Notify
telsendmsg(
    conf=tel_config,
    msg="global-plucking --- analysis_phillipscurve_slope_urate_ugap: COMPLETED",
)

# End
print("\n----- Ran in " + "{:.0f}".format(time.time() - time_start) + " seconds -----")

# %%