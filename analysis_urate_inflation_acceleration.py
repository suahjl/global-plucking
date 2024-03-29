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

# %%
# II --- Pre-analysis wrangling
# Trim countries
list_countries_keep = [
    "australia",
    "malaysia",
    "singapore",
    "thailand",
    # "indonesia",  # no urate data
    "philippines",  # no urate data
    "united_states",  # problems with BER
    "united_kingdom",
    "germany",
    "france",
    "italy",
    "japan",
    "south_korea",
    # "taiwan",  # not covered country
    # "hong_kong_sar_china_",  # no core inflation
    "india",  # no urate data
    # "china",  # special case
    "chile",
    "mexico",
    "brazil",
]
df = df[df["country"].isin(list_countries_keep)]
# Transform
cols_pretransformed = ["rgdp", "m2", "maxgepu", "expcpi"]
cols_levels = ["reer", "ber", "brent", "gepu"]
cols_rate = ["stir", "ltir", "privdebt", "privdebt_bank"]
cols_firstdiff = ["cpi", "corecpi"]
for col in cols_levels:
    df[col] = 100 * ((df[col] / df.groupby("country")[col].shift(4)) - 1)
for col in cols_rate:
    df[col] = df[col] - df.groupby("country")[col].shift(4)
for col in cols_firstdiff:
    df[col] = df[col] - df.groupby("country")[col].shift(1)
# Generate lagged terms for interacted variables
df["urate_int_urate_gap"] = df["urate"] * df["urate_gap"]
# Generate lags
for lag in range(1, 4 + 1):
    for col in cols_pretransformed + cols_levels + cols_rate + cols_firstdiff:
        df[col + "_lag" + str(lag)] = df.groupby("country")[col].shift(lag)
# Trim dates
df["quarter"] = pd.to_datetime(df["quarter"]).dt.to_period("q")
df = df[(df["quarter"] >= t_start_q) & (df["quarter"] <= t_end_q)]
# Reset index
df = df.reset_index(drop=True)
# Set numeric time index
df["time"] = df.groupby("country").cumcount()
dict_numerictime_quarter = dict(zip(df["time"], df["quarter"]))
del df["quarter"]

# %%
# II --- Analysis
# %%
# Chart settings
heatmaps_y_fontsize = 12
heatmaps_x_fontsize = 12
heatmaps_title_fontsize = 12
heatmaps_annot_fontsize = 12
list_file_names = []
# %%
# POLS
# Without REER
eqn = "corecpi ~ 1 + urate + expcpi + corecpi_lag1"
mod_pols, res_pols, params_table_pols, joint_teststats_pols, reg_det_pols = reg_ols(
    df=df, eqn=eqn
)
file_name = path_output + "urate_inflation_acceleration_params_pols"
list_file_names += [file_name]
chart_title = "Pooled OLS: Without REER (Without U-Rate Gap)"
fig = heatmap(
    input=params_table_pols,
    mask=False,
    colourmap="vlag",
    outputfile=file_name + ".png",
    title=chart_title,
    lb=params_table_pols.min().min(),
    ub=params_table_pols.max().max(),
    format=".4f",
    show_annot=True,
    y_fontsize=heatmaps_y_fontsize,
    x_fontsize=heatmaps_x_fontsize,
    title_fontsize=heatmaps_title_fontsize,
    annot_fontsize=heatmaps_annot_fontsize,
)
# telsendimg(conf=tel_config, path=file_name + ".png", cap=chart_title)
# With REER
eqn = "corecpi ~ 1 + urate + expcpi + corecpi_lag1 + reer"
(
    mod_pols_reer,
    res_pols_reer,
    params_table_pols_reer,
    joint_teststats_pols_reer,
    reg_det_pols_reer,
) = reg_ols(df=df, eqn=eqn)
file_name = path_output + "urate_inflation_acceleration_params_pols_reer"
list_file_names += [file_name]
chart_title = "Pooled OLS: With REER (Without U-Rate Gap)"
fig = heatmap(
    input=params_table_pols_reer,
    mask=False,
    colourmap="vlag",
    outputfile=file_name + ".png",
    title=chart_title,
    lb=params_table_pols_reer.min().min(),
    ub=params_table_pols_reer.max().max(),
    format=".4f",
    show_annot=True,
    y_fontsize=heatmaps_y_fontsize,
    x_fontsize=heatmaps_x_fontsize,
    title_fontsize=heatmaps_title_fontsize,
    annot_fontsize=heatmaps_annot_fontsize,
)
# telsendimg(conf=tel_config, path=file_name + ".png", cap=chart_title)

# %%
# FE
# Without REER
mod_fe, res_fe, params_table_fe, joint_teststats_fe, reg_det_fe = fe_reg(
    df=df,
    y_col="corecpi",
    x_cols=[
        "urate",
        "expcpi",
        "corecpi_lag1",
    ],
    i_col="country",
    t_col="time",
    fixed_effects=True,
    time_effects=False,
    cov_choice="robust",
)
file_name = path_output + "urate_inflation_acceleration_params_fe"
list_file_names += [file_name]
chart_title = "FE: Without REER (Without U-Rate Gap)"
fig = heatmap(
    input=params_table_fe,
    mask=False,
    colourmap="vlag",
    outputfile=file_name + ".png",
    title=chart_title,
    lb=params_table_fe.min().min(),
    ub=params_table_fe.max().max(),
    format=".4f",
    show_annot=True,
    y_fontsize=heatmaps_y_fontsize,
    x_fontsize=heatmaps_x_fontsize,
    title_fontsize=heatmaps_title_fontsize,
    annot_fontsize=heatmaps_annot_fontsize,
)
# telsendimg(conf=tel_config, path=file_name + ".png", cap=chart_title)
# With REER (benchmark model)
(
    mod_fe_reer,
    res_fe_reer,
    params_table_fe_reer,
    joint_teststats_fe_reer,
    reg_det_fe_reer,
) = fe_reg(
    df=df,
    y_col="corecpi",
    x_cols=[
        "urate",
        "expcpi",
        # "corecpi_lag1",
        "reer",
    ],
    i_col="country",
    t_col="time",
    fixed_effects=True,
    time_effects=False,
    cov_choice="robust",
)
file_name = path_output + "urate_inflation_acceleration_params_fe_reer"
list_file_names += [file_name]
chart_title = "FE: With REER (Without U-Rate Gap)"
fig = heatmap(
    input=params_table_fe_reer,
    mask=False,
    colourmap="vlag",
    outputfile=file_name + ".png",
    title=chart_title,
    lb=params_table_fe_reer.min().min(),
    ub=params_table_fe_reer.max().max(),
    format=".4f",
    show_annot=True,
    y_fontsize=heatmaps_y_fontsize,
    x_fontsize=heatmaps_x_fontsize,
    title_fontsize=heatmaps_title_fontsize,
    annot_fontsize=heatmaps_annot_fontsize,
)
# telsendimg(conf=tel_config, path=file_name + ".png", cap=chart_title)
params_table_fe_reer.to_parquet(file_name + ".parquet")

# %%
# Compile all log likelihoods
df_loglik = pd.DataFrame(
    {
        "Model": [
            "POLS: Without REER",
            "POLS: With REER",
            "FE: Without REER",
            "FE: With REER",
        ],
        "AICc": [
            (-2 * res_pols.llf + 2 * res_pols.df_model)
            + (
                (2 * res_pols.df_model * (res_pols.df_model + 1))
                / (res_pols.nobs - res_pols.df_model - 1)
            ),
            (-2 * res_pols_reer.llf + 2 * res_pols_reer.df_model)
            + (
                (2 * res_pols_reer.df_model * (res_pols_reer.df_model + 1))
                / (res_pols_reer.nobs - res_pols_reer.df_model - 1)
            ),
            (-2 * res_fe.loglik + 2 * res_fe.df_model)
            + (
                (2 * res_fe.df_model * (res_fe.df_model + 1))
                / (res_fe.entity_info.total - res_fe.df_model - 1)
            ),
            (-2 * res_fe_reer.loglik + 2 * res_fe_reer.df_model)
            + (
                (2 * res_fe_reer.df_model * (res_fe_reer.df_model + 1))
                / (res_fe_reer.entity_info.total - res_fe_reer.df_model - 1)
            ),
        ],
        "AIC": [
            (-2 * res_pols.llf + 2 * res_pols.df_model),
            (-2 * res_pols_reer.llf + 2 * res_pols_reer.df_model),
            (-2 * res_fe.loglik + 2 * res_fe.df_model),
            (-2 * res_fe_reer.loglik + 2 * res_fe_reer.df_model),
        ],
        "Log-Likelihood": [
            res_pols.llf,
            res_pols_reer.llf,
            res_fe.loglik,
            res_fe_reer.loglik,
        ],
    }
)
df_loglik = pd.DataFrame(df_loglik.set_index("Model"))
file_name = path_output + "urate_inflation_acceleration_loglik"
list_file_names += [file_name]
chart_title = "AICs and Log-Likelihood of Estimated Models \n(Without U-Rate Gap)"
fig = heatmap(
    input=df_loglik,
    mask=False,
    colourmap="vlag",
    outputfile=file_name + ".png",
    title=chart_title,
    lb=df_loglik.min().min(),
    ub=df_loglik.max().max(),
    format=".4f",
    show_annot=True,
    y_fontsize=heatmaps_y_fontsize,
    x_fontsize=heatmaps_x_fontsize,
    title_fontsize=heatmaps_title_fontsize,
    annot_fontsize=heatmaps_annot_fontsize,
)
# telsendimg(conf=tel_config, path=file_name + ".png", cap=chart_title)


# %%
# Regression-implied NAIRU
df_nairu = df.merge(res_fe_reer.estimated_effects.reset_index(drop=False))
df_nairu = df_nairu.merge(res_fe_reer.resids.reset_index(drop=False))
df_nairu["time"] = df_nairu["time"].replace(dict_numerictime_quarter)
df_nairu = df_nairu.rename(columns={"time": "quarter"})
df_nairu["fit_check"] = (
    (df_nairu["estimated_effects"])
    + (res_fe_reer.params.urate * df_nairu["urate"])
    + (res_fe_reer.params.expcpi * df_nairu["expcpi"])
    + (res_fe_reer.params.reer * df_nairu["reer"])
    # + (res_fe_reer.params.corecpi_lag1 * df_nairu["corecpi_lag1"])
    + (df_nairu["residual"])
)
df_nairu["nairu"] = (
    -1
    * (
        (df_nairu["estimated_effects"])
        + (res_fe_reer.params.expcpi * df_nairu["expcpi"])
        + (res_fe_reer.params.reer * df_nairu["reer"])
        # + (res_fe_reer.params.corecpi_lag1 * df_nairu["corecpi_lag1"])
    )
    / (res_fe_reer.params.urate)
)
countries_asean4 = ["malaysia", "thailand", "philippines"]
countries_asianie = [
    "singapore",
    "south_korea",
]
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
nested_list_country_groups = [
    countries_asean4,
    countries_asianie,
    countries_bigemerging,
    countries_adv,
]
nice_group_names_by_country_groups = ["ASEAN-4", "Asian NIEs", "Major EMs", "AEs"]
snakecase_group_names_by_country_groups = ["asean4", "asianie", "bigemerging", "adv"]
rows_by_country_groups = [2, 1, 2, 3]
cols_by_country_groups = [2, 2, 2, 3]
for country_groups, snakecase_group_name, nice_group_name, n_rows, n_cols in tqdm(
    zip(
        nested_list_country_groups,
        snakecase_group_names_by_country_groups,
        nice_group_names_by_country_groups,
        rows_by_country_groups,
        cols_by_country_groups,
    )
):
    df_sub = df_nairu[df_nairu["country"].isin(country_groups)].copy()
    df_sub["quarter"] = df_sub["quarter"].astype("str")
    fig = subplots_linecharts(
        data=df_sub,
        col_group="country",
        cols_values=["urate", "urate_ceiling", "nairu"],
        cols_values_nice=["U-Rate", "U-Rate Floor", "Implied NAIRU"],
        col_time="quarter",
        annot_size=12,
        font_size=12,
        line_colours=["black", "crimson", "darkblue"],
        line_dashes=["solid", "solid", "solid"],
        main_title="U-Rate (Actual, Floor, NAIRU) in " + nice_group_name,
        maxrows=n_rows,
        maxcols=n_cols,
    )
    file_name = (
        path_output
        + "urate_inflation_acceleration_params_floorversusnairu"
        + snakecase_group_name
    )
    fig.write_image(file_name + ".png")
    # telsendimg(
    #     conf=tel_config,
    #     path=file_name + ".png",
    #     cap=file_name
    # )
    list_file_names += [file_name]

# %%
# Compile all heat maps
file_name_pdf = path_output + "urate_inflation_acceleration_params"
pil_img2pdf(list_images=list_file_names, extension="png", pdf_name=file_name_pdf)
telsendfiles(conf=tel_config, path=file_name_pdf + ".pdf", cap=file_name_pdf)

# %%
# X --- Notify
telsendmsg(
    conf=tel_config,
    msg="global-plucking --- analysis_urate_inflation_acceleration: COMPLETED",
)

# End
print("\n----- Ran in " + "{:.0f}".format(time.time() - time_start) + " seconds -----")

# %%
