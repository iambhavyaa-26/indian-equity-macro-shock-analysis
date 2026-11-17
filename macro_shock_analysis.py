"""Macro Shocks and Indian Sectors: full analysis in one script.

Reads Project3_Raw_Data.xlsx (same folder) and runs: change calculation, sample cleaning,
HAC regressions per sector, diagnostics, heatmap, stability checks, stress test and VaR.
Run:  pip install pandas numpy statsmodels matplotlib openpyxl   then   python macro_shock_analysis.py
Outputs saved next to the script: regression_data.csv, heatmap.png, coefficients.csv, pvalues.csv,
stress_all.csv, stress_reliable.csv, var.csv.
"""

import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import durbin_watson, jarque_bera
from statsmodels.stats.outliers_influence import variance_inflation_factor
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
pd.set_option("display.width", 200); pd.set_option("display.max_columns", None); pd.set_option("display.float_format", lambda x: f"{x:,.3f}")

# Raw monthly data: index closes, Brent, USD/INR, repo level, CPI (as announced)
raw = pd.read_excel("Project3_Raw_Data.xlsx", sheet_name="Raw_Data").set_index("Month")
print("Months:", len(raw), "|", raw.index[0], "to", raw.index[-1])

# Levels -> changes: % change for prices, change in percentage points for repo and CPI
R = pd.DataFrame(index=raw.index)
R["N50"]  = raw.Nifty50.pct_change() * 100
R["BANK"] = raw.NiftyBank.pct_change() * 100
R["IT"]   = raw.NiftyIT.pct_change() * 100
R["FMCG"] = raw.NiftyFMCG.pct_change() * 100
R["dREPO"] = raw.Repo.diff()
R["dCPI"]  = raw.CPI.diff()
R["OIL"]   = raw.Brent.pct_change() * 100
R["FX"]    = raw.USDINR.pct_change() * 100

# Drop months with unusable CPI data; flag March 2020 (Covid crash) with a dummy
DROP = ["2020-05", "2020-06", "2020-07", "2026-02"]
R["COVID"] = (R.index == "2020-03").astype(int)
S = R.drop(index=DROP).dropna()
SECTORS = {"BANK": "Nifty Bank", "IT": "Nifty IT", "FMCG": "Nifty FMCG", "N50": "Nifty 50 (market)"}
MACRO = ["dREPO", "dCPI", "OIL", "FX"]
X = MACRO + ["COVID"]
print("Months used in regression:", len(S), "(", S.index[0], "to", S.index[-1], ")")
print(S.head())
S.to_csv("regression_data.csv")   # the 99-month sample used in the regressions


hac = lambda y, cols=X, d=S: sm.OLS(d[y], sm.add_constant(d[cols])).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
plain = lambda y, cols=X, d=S: sm.OLS(d[y], sm.add_constant(d[cols])).fit()
M = {k: hac(k) for k in SECTORS}
coef = pd.DataFrame({SECTORS[k]: M[k].params[MACRO] for k in SECTORS}).T
pval = pd.DataFrame({SECTORS[k]: M[k].pvalues[MACRO] for k in SECTORS}).T
print("R-squared:", {SECTORS[k]: round(M[k].rsquared, 3) for k in SECTORS})
print("\nCoefficients (effect on monthly return, % points):"); print(coef)
print("p-values (< 0.10 = reliable):"); print(pval)

# Diagnostics
Xf = sm.add_constant(S[X])
diag = pd.DataFrame({SECTORS[k]: {"R-squared": plain(k).rsquared, "Durbin-Watson": durbin_watson(plain(k).resid), "Breusch-Pagan p": het_breuschpagan(plain(k).resid, Xf)[1], "Jarque-Bera p": jarque_bera(plain(k).resid)[1]} for k in SECTORS}).T
print(diag)
print("VIF:", {c: round(variance_inflation_factor(Xf.values, i), 2) for i, c in enumerate(Xf.columns) if c != "const"})

# Heatmap: effect of a 1-standard-deviation shock = coefficient x std dev of the shock
sd = S[MACRO].std(ddof=1)
effect = coef * sd
labels = [f"Repo up\n(1 SD = {sd.dREPO:.2f} pp)", f"Inflation up\n(1 SD = {sd.dCPI:.2f} pp)", f"Oil up\n(1 SD = {sd.OIL:.1f}%)", f"Rupee weaker\n(1 SD = {sd.FX:.2f}%)"]
star = lambda p: "**" if p < .05 else ("*" if p < .10 else "")
fig, ax = plt.subplots(figsize=(8.5, 4.4), dpi=130)
im = ax.imshow(effect.values, cmap=LinearSegmentedColormap.from_list("d", ["#e34948", "#f0efec", "#2a78d6"]), vmin=-2.6, vmax=2.6, aspect="auto")
_ = [ax.text(j, i, f"{effect.values[i,j]:+.2f}{star(pval.values[i,j])}", ha="center", va="center", fontsize=12, fontweight="bold" if star(pval.values[i,j]) else "normal") for i in range(4) for j in range(4)]
ax.set_xticks(range(4)); ax.set_xticklabels(labels, fontsize=9); ax.set_yticks(range(4)); ax.set_yticklabels(effect.index)
ax.xaxis.tick_top(); ax.tick_params(length=0)
_ = [s.set_visible(False) for s in ax.spines.values()]
fig.colorbar(im, ax=ax, fraction=0.035).set_label("Change in monthly return (% points)")
fig.text(0.01, 0.01, "Only the rupee column is statistically reliable. ** p<0.05, * p<0.10", fontsize=8)
fig.tight_layout(); fig.savefig("heatmap.png"); plt.close()
print(effect.round(2))


fmt = lambda m, v: f"{m.params[v]:+.2f} (p={m.pvalues[v]:.2f})"
view = lambda sub, cols: pd.DataFrame({SECTORS[k]: {"Repo": fmt(hac(k, cols, sub), "dREPO"), "Oil": fmt(hac(k, cols, sub), "OIL"), "Rupee": fmt(hac(k, cols, sub), "FX")} for k in SECTORS}).T
a, b = S[S.index <= "2021-12"], S[S.index >= "2022-01"]   # 2018-21 includes the Covid dummy; 2022-26 has no Covid month
print(f"2018-2021 (n={len(a)})"); print(view(a, X))
print(f"2022-2026 (n={len(b)})"); print(view(b, MACRO))
print("Full sample WITHOUT the Covid dummy:"); print(view(S, MACRO))

# Stress test = coefficient x shock size
scen = pd.DataFrame({"dREPO": [1, 0, 0, 1], "dCPI": [0, 0, 0, 1], "OIL": [0, 20, 0, 20], "FX": [0, 0, 5, 5]}, index=["A. Repo +1 pp", "B. Oil +20%", "C. Rupee 5% weaker", "D. All combined"])
allc = pd.DataFrame({SECTORS[k]: scen @ M[k].params[MACRO] for k in SECTORS})
rel = pd.DataFrame({SECTORS[k]: scen @ M[k].params[MACRO].where(M[k].pvalues[MACRO] < .10, 0) for k in SECTORS})
print("Stress test, all coefficients:"); print(allc.round(1))
print("Stress test, reliable coefficients only (p<0.10):"); print(rel.round(1))

# Historical 95% VaR = 5th percentile of monthly returns
var = pd.DataFrame({n: {"avg month %": R[k].mean(), "std dev %": R[k].std(), "95% VaR %": np.nanpercentile(R[k], 5), "worst month %": R[k].min(), "worst month": R[k].idxmin()} for k, n in SECTORS.items()}).T
var["Loss on Rs 10 lakh at 95% VaR"] = (-var["95% VaR %"].astype(float) / 100 * 1_000_000).round(0)
print(var)
coef.to_csv('coefficients.csv'); pval.to_csv('pvalues.csv'); allc.to_csv('stress_all.csv'); rel.to_csv('stress_reliable.csv'); var.to_csv('var.csv')
