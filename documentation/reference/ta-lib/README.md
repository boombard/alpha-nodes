# TA-Lib function reference

A verbatim local snapshot of TA-Lib's per-function documentation, for agents choosing or
specifying technical indicators (formula, inputs, params, defaults, notes). Design context:
[finance.md, Technical analysis and TA-Lib](../../design/finance.md). TA-Lib is also a dev
dependency, used as a test oracle for our own calcs.

- Source: https://github.com/TA-Lib/ta-lib/tree/6435b2adf5c51ad60d70f2912ab584de0ee86614/website/src/functions
- Commit: `6435b2adf5c51ad60d70f2912ab584de0ee86614`
- Fetched: 2026-11-25
- Pages: 248 in [functions/](functions/), of which 246 are functions (the rest,
  `index.md` and `stability.md`, are prose); 237 functions are exposed by the pinned
  ta-lib-python 0.8.3 (`talib.get_functions()`). The docs on TA-Lib `main` can run ahead of
  the released wrapper: pages marked `no` below are kept but cannot be called from Python.
- Pages are unmodified, so chart links, CSV links and `/functions/...` links inside them
  point at the TA-Lib website, not at this repo. The reference CSVs and SVGs are not stored.

## Licence

TA-Lib is BSD-3-Clause. Notice, reproduced from the source repository's `LICENSE`:

```text
Copyright (c) 1999-2026, Mario Fortier

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Refresh

```sh
uv run python packages/alpha_nodes/scripts/sync_talib_reference.py [--commit SHA]
```

Without `--commit` the script pins current `main` HEAD. It rewrites `functions/*.md` and this
file; review the diff and bump the ta-lib-python pin in the root `pyproject.toml` if the
wrapper has moved. Never hand-edit the pages.

## Index

Columns: inputs are the page's input series (`real` is a generic series); params show
`name=default`. Group is the wrapper's where it knows the function, else the page's.

### Cycle Indicators

| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python 0.8.3 |
| --- | --- | --- | --- | --- | --- |
| [HT_DCPERIOD](functions/ht_dcperiod.md) | Hilbert Transform - Dominant Cycle Period (HT_DCPERIOD) | Hilbert Transform estimate of the dominant cycle period (in bars) of the price series. Outputs the smoothed instantaneous cycle period. | real | none | yes |
| [HT_DCPHASE](functions/ht_dcphase.md) | Hilbert Transform - Dominant Cycle Phase (HT_DCPHASE) | Hilbert Transform Dominant Cycle Phase: the instantaneous phase (in degrees) of the dominant market cycle, derived from a homodyne discriminator on a… | real | none | yes |
| [HT_PHASOR](functions/ht_phasor.md) | Hilbert Transform - Phasor Components (HT_PHASOR) | Hilbert Transform indicator that decomposes the price series into its in-phase (I) and quadrature (Q) phasor components. | real | none | yes |
| [HT_SINE](functions/ht_sine.md) | Hilbert Transform - SineWave (HT_SINE) | Hilbert Transform SineWave: derives the dominant-cycle phase from price and emits its sine plus a 45-degree-lead sine. | real | none | yes |
| [HT_TRENDMODE](functions/ht_trendmode.md) | Hilbert Transform - Trend vs Cycle Mode (HT_TRENDMODE) | Hilbert Transform classifier that labels each bar 1 (trending — favor trend-following) or 0 (cycling — favor mean-reversion). | real | none | yes |
| [SWAK_2PHP](functions/swak_2php.md) | Swiss Army Knife - Two-Pole High-Pass Filter (SWAK_2PHP) | The two-pole high-pass row of John Ehlers' Swiss Army Knife filter: the same double real pole the Gaussian and Butterworth rows use, with a detrending… | real | timePeriod=20 | yes |
| [SWAK_BP](functions/swak_bp.md) | Swiss Army Knife - Band-Pass Filter (SWAK_BP) | The band-pass row of John Ehlers' Swiss Army Knife filter: a cycle extractor that keeps a band of periods around a chosen centre and removes everything… | real | timePeriod=20, delta=0.1 | yes |
| [SWAK_HP](functions/swak_hp.md) | Swiss Army Knife - High-Pass Filter (SWAK_HP) | The high-pass row of John Ehlers' Swiss Army Knife filter: a one-pole detrender that removes what is slower than the cutoff period and keeps what is… | real | timePeriod=20 | yes |

### Math Operators

| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python 0.8.3 |
| --- | --- | --- | --- | --- | --- |
| [ADD](functions/add.md) | Vector Arithmetic Add (ADD) | Element-wise addition of two input series. | real0, real1 | none | yes |
| [CUMSUM](functions/cumsum.md) | Cumulative Sum (CUMSUM) | Cumulative Sum: the running total of a series from the anchor bar forward. | real | none | yes |
| [DIV](functions/div.md) | Vector Arithmetic Div (DIV) | Element-wise division of two input series. | real0, real1 | none | yes |
| [MAX](functions/max.md) | Highest value over a specified period (MAX) | Highest input value over a rolling window of the last optInTimePeriod bars. A moving-window maximum. | real | timePeriod=30 | yes |
| [MAXINDEX](functions/maxindex.md) | Index of highest value over a specified period (MAXINDEX) | Returns the index of the highest input value within a rolling window of optInTimePeriod bars. Same as MAX but outputs the location instead of the value. | real | timePeriod=30 | yes |
| [MIN](functions/min.md) | Lowest value over a specified period (MIN) | Rolling minimum: the lowest input value over the trailing period. | real | timePeriod=30 | yes |
| [MININDEX](functions/minindex.md) | Index of lowest value over a specified period (MININDEX) | Returns the absolute index of the lowest value within a rolling window of the given period. | real | timePeriod=30 | yes |
| [MINMAX](functions/minmax.md) | Lowest and highest values over a specified period (MINMAX) | Returns both the lowest and highest values of the input over a rolling window of the last optInTimePeriod bars. | real | timePeriod=30 | yes |
| [MINMAXINDEX](functions/minmaxindex.md) | Indexes of lowest and highest values over a specified period (MINMAXINDEX) | Returns the absolute input indices of the lowest and highest values within each rolling window of optInTimePeriod bars. Index variant of MINMAX. | real | timePeriod=30 | yes |
| [MULT](functions/mult.md) | Vector Arithmetic Mult (MULT) | Element-wise multiplication of two input series. | real0, real1 | none | yes |
| [SUB](functions/sub.md) | Vector Arithmetic Subtraction (SUB) | Element-wise subtraction of two input series. | real0, real1 | none | yes |
| [SUM](functions/sum.md) | Summation (SUM) | Rolling sum of the input over a fixed period. Each output is the sum of the most recent optInTimePeriod input values. | real | timePeriod=30 | yes |

### Math Transform

| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python 0.8.3 |
| --- | --- | --- | --- | --- | --- |
| [ACOS](functions/acos.md) | Vector Trigonometric ACos (ACOS) | Element-wise arc cosine of the input series. | real | none | yes |
| [ASIN](functions/asin.md) | Vector Trigonometric ASin (ASIN) | Element-wise arcsine of the input series. | real | none | yes |
| [ATAN](functions/atan.md) | Vector Trigonometric ATan (ATAN) | Element-wise arctangent of the input series. | real | none | yes |
| [CEIL](functions/ceil.md) | Vector Ceil (CEIL) | Element-wise ceiling (round up to the nearest integer) of the input series. | real | none | yes |
| [COS](functions/cos.md) | Vector Trigonometric Cos (COS) | Element-wise cosine of the input series. | real | none | yes |
| [COSH](functions/cosh.md) | Vector Trigonometric Cosh (COSH) | Element-wise hyperbolic cosine of the input series. | real | none | yes |
| [EXP](functions/exp.md) | Vector Arithmetic Exp (EXP) | Element-wise base-e exponential of the input series. | real | none | yes |
| [FLOOR](functions/floor.md) | Vector Floor (FLOOR) | Element-wise floor (round down to the nearest integer) of the input series. | real | none | yes |
| [LN](functions/ln.md) | Vector Log Natural (LN) | Element-wise natural logarithm of the input series. | real | none | yes |
| [LOG10](functions/log10.md) | Vector Log10 (LOG10) | Element-wise base-10 logarithm of the input series. | real | none | yes |
| [SIN](functions/sin.md) | Vector Trigonometric Sin (SIN) | Element-wise sine of the input series. | real | none | yes |
| [SINH](functions/sinh.md) | Vector Trigonometric Sinh (SINH) | Element-wise hyperbolic sine of the input series. | real | none | yes |
| [SQRT](functions/sqrt.md) | Vector Square Root (SQRT) | Element-wise square root of the input series. | real | none | yes |
| [TAN](functions/tan.md) | Vector Trigonometric Tan (TAN) | Element-wise tangent of the input series. | real | none | yes |
| [TANH](functions/tanh.md) | Vector Trigonometric Tanh (TANH) | Element-wise hyperbolic tangent of the input series. | real | none | yes |

### Momentum Indicators

| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python 0.8.3 |
| --- | --- | --- | --- | --- | --- |
| [AC](functions/ac.md) | Accelerator/Decelerator Oscillator (AC) | Bill Williams' Accelerator/Decelerator Oscillator (New Trading Dimensions, 1998): the rate at which market momentum is itself speeding up or slowing down. | high, low | fastPeriod=5, slowPeriod=34, signalPeriod=5 | yes |
| [ADX](functions/adx.md) | Average Directional Movement Index (ADX) | Wilder's Average Directional Movement Index, a smoothed measure of trend strength derived from the directional indicators (+DI/-DI). | high, low, close | timePeriod=14 | yes |
| [ADXR](functions/adxr.md) | Average Directional Movement Index Rating (ADXR) | Smoothed variant of ADX: the average of the current ADX value and the ADX value from (period-1) bars earlier. Further damps ADX to gauge trend strength. | high, low, close | timePeriod=14 | yes |
| [AO](functions/ao.md) | Awesome Oscillator (AO) | Bill Williams' Awesome Oscillator (New Trading Dimensions, 1998): market momentum read as the spread between a short and a long simple moving average of… | high, low | fastPeriod=5, slowPeriod=34 | yes |
| [APO](functions/apo.md) | Absolute Price Oscillator (APO) | Absolute Price Oscillator: the difference between a fast and a slow moving average of the input, in price units. Measures short- vs long-term momentum. | real | fastPeriod=12, slowPeriod=26, mAType=EMA (1) | yes |
| [AROON](functions/aroon.md) | Aroon (AROON) | Aroon reports how recently the highest high and lowest low occurred within a rolling window of length optInTimePeriod, as two 0-100 oscillators. | high, low | timePeriod=14 | yes |
| [AROONOSC](functions/aroonosc.md) | Aroon Oscillator (AROONOSC) | Aroon Oscillator: AroonUp minus AroonDown over a lookback window. Measures trend direction and strength on a -100..+100 scale. | high, low | timePeriod=14 | yes |
| [ASI](functions/asi.md) | Wilder Accumulative Swing Index (ASI) | Wilder's Accumulative Swing Index: the running total of the Swing Index (SI), a line meant to trace the market's real swings through the noise of the… | open, high, low, close | limitMove=3 | yes |
| [BOP](functions/bop.md) | Balance Of Power (BOP) | Balance Of Power compares where the close sits relative to the open, normalized by the bar's high-low range. A per-bar oscillator with no smoothing. | open, high, low, close | none | yes |
| [CCI](functions/cci.md) | Commodity Channel Index (CCI) | Commodity Channel Index: measures the current typical price relative to its simple moving average, scaled by mean absolute deviation. | high, low, close | timePeriod=14 | yes |
| [CG](functions/cg.md) | Center of Gravity Oscillator (CG) | John Ehlers' Center of Gravity oscillator: the balance point of the last optInTimePeriod values, each weighted by its value and placed at its position… | real | timePeriod=10 | yes |
| [CHOP](functions/chop.md) | Choppiness Index (CHOP) | Choppiness Index: a trend-versus-consolidation gauge, the true range travelled over a window against the height of the box its bars span. | high, low, close | timePeriod=14 | yes |
| [CHOPTR](functions/choptr.md) | Choppiness Index (True Range Box) (CHOPTR) | Choppiness Index with a true-range box: the true range travelled over a window against the span from its highest true high to its lowest true low. | high, low, close | timePeriod=14 | yes |
| [CMO](functions/cmo.md) | Chande Momentum Oscillator (CMO) | Chande Momentum Oscillator: bounded momentum measure from Wilder-smoothed average up-moves and down-moves. | real | timePeriod=14 | yes |
| [CMOU](functions/cmou.md) | Chande Momentum Oscillator (Unsmoothed) (CMOU) | Chande Momentum Oscillator: Tushar Chande's original momentum oscillator, computed from plain moving-window sums of the up-moves and down-moves over the… | real | timePeriod=14 | yes |
| [COPPOCK](functions/coppock.md) | Coppock Curve (COPPOCK) | Coppock Curve: Edwin S. "Sedge" Coppock's long-term momentum oscillator (Barron's, originally published as the "Trendex Model"), computed as a weighted… | real | wMAPeriod=10, rOC1Period=11, rOC2Period=14 | yes |
| [CRSI](functions/crsi.md) | Connors Relative Strength Index (CRSI) | Connors RSI: a 0 to 100 oscillator, the plain average of three short-term momentum readings on that same scale. | real | timePeriod=3, streakPeriod=2, rankPeriod=100 | yes |
| [CTI](functions/cti.md) | Correlation Trend Indicator (CTI) | John F. Ehlers' Correlation Trend Indicator: the Pearson correlation of the last optInTimePeriod closes against a straight line of positive slope. | real | timePeriod=20 | yes |
| [DOSC](functions/dosc.md) | Derivative Oscillator (DOSC) | Derivative Oscillator: Wilder's RSI, smoothed by two exponential averages in series, with a simple average of that smoothed line subtracted from it. | real | timePeriod=14, firstPeriod=5, secondPeriod=3, signalPeriod=9 | yes |
| [DPO](functions/dpo.md) | Detrended Price Oscillator (DPO) | Detrended Price Oscillator: the price a half-cycle back, less the moving average that spans the cycle. | real | timePeriod=20 | yes |
| [DX](functions/dx.md) | Directional Movement Index (DX) | Wilder's Directional Movement Index: the normalized spread between +DI and -DI. | high, low, close | timePeriod=14 | yes |
| [ER](functions/er.md) | Kaufman Efficiency Ratio (ER) | Kaufman Efficiency Ratio (also searched as "KER"): Perry Kaufman's noise measure from Smarter Trading (1995) — the net directional movement over the… | real | timePeriod=10 | yes |
| [ERI](functions/eri.md) | Elder Ray Index (Bull Power / Bear Power) (ERI) | Elder Ray Index: Alexander Elder's Bull Power / Bear Power pair from Trading for a Living (1993) — how far the bar's high and low sit from an EMA of the… | high, low, close | timePeriod=13 | yes |
| [FISHER](functions/fisher.md) | Fisher Transform (FISHER) | Ehlers' Fisher Transform: an oscillator that reshapes the midpoint's position in its rolling channel into a near-normal distribution. | high, low | timePeriod=10 | yes |
| [FOSC](functions/fosc.md) | Forecast Oscillator (FOSC) | Forecast Oscillator: the percentage by which the close deviates from the Time Series Forecast that was made one bar earlier for the current bar. | real | timePeriod=5 | yes |
| [FRACTAL](functions/fractal.md) | Williams Fractal (FRACTAL) | Williams Fractal: a causal swing-pivot detector. | high, low | leftBars=2, rightBars=2 | yes |
| [GATOR](functions/gator.md) | Gator Oscillator (GATOR) | Bill Williams' Gator Oscillator: how far apart the three Alligator lines are, as two histograms. | high, low | jawPeriod=13, jawShift=8, teethPeriod=8, teethShift=5, lipsPeriod=5, lipsShift=3 | no |
| [IBS](functions/ibs.md) | Internal Bar Strength (IBS) | Internal Bar Strength: where the close sits inside its own bar's range. | high, low, close | none | yes |
| [IMI](functions/imi.md) | Intraday Momentum Index (IMI) | Intraday Momentum Index: an RSI-like 0-100 oscillator built from the open-to-close body of each bar. | open, close | timePeriod=14 | yes |
| [KDJ](functions/kdj.md) | KDJ Stochastic (KDJ) | The stochastic oscillator as it is drawn on Chinese-market platforms: the Slow-%K and Slow-%D lines plus a third line J that amplifies the gap between… | high, low, close | fastK_Period=9, slowK_Period=3, slowK_MAType=RMA (13), slowD_Period=3, slowD_MAType=RMA (13) | yes |
| [KST](functions/kst.md) | Know Sure Thing (Pring) (KST) | Know Sure Thing: Martin J. Pring's momentum oscillator, a weighted sum of four smoothed rates of change with a moving-average signal line. | real | rOC1Period=10, rOC2Period=15, rOC3Period=20, rOC4Period=30, sMA1Period=10, sMA2Period=10, sMA3Period=10, sMA4Period=15, signalPeriod=9 | yes |
| [KSTEXT](functions/kstext.md) | Know Sure Thing with controllable MA type (KSTEXT) | Know Sure Thing with selectable moving averages: Pring's weighted sum of four smoothed rates of change, with a signal line. | real | rOC1Period=10, rOC2Period=15, rOC3Period=20, rOC4Period=30, mA1Period=10, mA2Period=10, mA3Period=10, mA4Period=15, signalPeriod=9, rOCMAType=SMA (0), signalMAType=SMA (0) | yes |
| [MACD](functions/macd.md) | Moving Average Convergence/Divergence (MACD) | Moving Average Convergence/Divergence: the difference between a fast and a slow EMA of the input, plus an EMA-smoothed signal line and their histogram. | real | fastPeriod=12, slowPeriod=26, signalPeriod=9 | yes |
| [MACDEXT](functions/macdext.md) | MACD with controllable MA type (MACDEXT) | MACD variant where the fast, slow, and signal moving averages each use a user-selectable MA type. | real | fastPeriod=12, fastMAType=SMA (0), slowPeriod=26, slowMAType=SMA (0), signalPeriod=9, signalMAType=SMA (0) | yes |
| [MACDFIX](functions/macdfix.md) | Moving Average Convergence/Divergence Fix 12/26 (MACDFIX) | MACD with the fast/slow EMAs fixed to the classic 12/26 periods (with the classic fixed smoothing factors 0.15 and 0.075), exposing only the signal period. | real | signalPeriod=9 | yes |
| [MACDV](functions/macdv.md) | MACD-V, Volatility Normalised Momentum (MACDV) | MACD-V, Alex Spiroglou's volatility-normalised MACD: the spread of a fast and a slow EMA of the close over the Average True Range, times 100. | high, low, close | fastPeriod=12, slowPeriod=26, signalPeriod=9 | no |
| [MFI](functions/mfi.md) | Money Flow Index (MFI) | Money Flow Index: a volume-weighted momentum oscillator (0-100) comparing positive vs negative money flow over a period. | high, low, close, volume | timePeriod=14 | yes |
| [MINUS_DI](functions/minus_di.md) | Minus Directional Indicator (MINUS_DI) | Wilder's Minus Directional Indicator: the Wilder-smoothed downward directional movement (-DM) normalized by smoothed True Range. | high, low, close | timePeriod=14 | yes |
| [MINUS_DM](functions/minus_dm.md) | Minus Directional Movement (MINUS_DM) | Minus Directional Movement, the downward component of Wilder's directional movement system. Measures Wilder-smoothed downward price motion over the period. | high, low | timePeriod=14 | yes |
| [MOM](functions/mom.md) | Momentum (MOM) | Momentum: current price minus the price optInTimePeriod bars ago. The absolute (unnormalized) rate of change. | real | timePeriod=10 | yes |
| [PLUS_DI](functions/plus_di.md) | Plus Directional Indicator (PLUS_DI) | Plus Directional Indicator: the Wilder-smoothed positive directional movement expressed as a percentage of the true range. | high, low, close | timePeriod=14 | yes |
| [PLUS_DM](functions/plus_dm.md) | Plus Directional Movement (PLUS_DM) | Plus Directional Movement: the Wilder-smoothed accumulation of upward directional movement (+DM1). | high, low | timePeriod=14 | yes |
| [PPO](functions/ppo.md) | Percentage Price Oscillator (PPO) | Percentage Price Oscillator: the difference between a fast and slow moving average expressed as a percentage of the slow MA. | real | fastPeriod=12, slowPeriod=26, mAType=EMA (1) | yes |
| [PSO](functions/pso.md) | Premier Stochastic Oscillator (PSO) | Premier Stochastic Oscillator: a short-period Fast %K, recentred on zero and rescaled, double-smoothed and then squashed into the range -1 to +1. | high, low, close | fastK_Period=8, eMAPeriod=5 | yes |
| [QSTICK](functions/qstick.md) | Qstick (QSTICK) | Tushar Chande and Stanley Kroll's Qstick (The New Technical Trader, 1994): a simple moving average of the candle body, close minus open. | open, close | timePeriod=10 | yes |
| [ROC](functions/roc.md) | Rate of change : ((price/prevPrice)-1)*100 (ROC) | Rate-of-change momentum oscillator: the percent change of price versus the price optInTimePeriod bars earlier. | real | timePeriod=10 | yes |
| [ROCP](functions/rocp.md) | Rate of change Percentage: (price-prevPrice)/prevPrice (ROCP) | Rate of change expressed as a fraction of the price optInTimePeriod bars ago. | real | timePeriod=10 | yes |
| [ROCR](functions/rocr.md) | Rate of change ratio: (price/prevPrice) (ROCR) | Rate of Change Ratio: the ratio of the current price to the price optInTimePeriod bars ago. A momentum measure centered at 1. | real | timePeriod=10 | yes |
| [ROCR100](functions/rocr100.md) | Rate of change ratio 100 scale: (price/prevPrice)*100 (ROCR100) | Rate-of-change ratio scaled by 100: current price as a percentage of the price optInTimePeriod bars ago. | real | timePeriod=10 | yes |
| [RSI](functions/rsi.md) | Relative Strength Index (RSI) | Wilder's Relative Strength Index, a momentum oscillator bounded 0-100 from the ratio of average gains to average losses over the period. | real | timePeriod=14 | yes |
| [SI](functions/si.md) | Wilder Swing Index (SI) | Wilder's Swing Index: one number rating each bar against the bar before it, from both bars' open and close and the current bar's high and low, signed by… | open, high, low, close | limitMove=3 | yes |
| [SMI](functions/smi.md) | Stochastic Momentum Index (SMI) | Stochastic Momentum Index: where the close sits relative to the midpoint of the recent high/low range, double-smoothed. | high, low, close | timePeriod=13, fastPeriod=2, slowPeriod=25, signalPeriod=9 | yes |
| [SQZMOM](functions/sqzmom.md) | Squeeze Momentum and Level (SQZMOM) | John Carter's TTM Squeeze, in the form LazyBear published on TradingView in 2014. | high, low, close | bBPeriod=20, nbDev=2, kCPeriod=20, factorWide=2, factorNormal=1.5, factorNarrow=1 | yes |
| [STC](functions/stc.md) | Schaff Trend Cycle (STC) | Schaff Trend Cycle (Doug Schaff): a MACD line passed twice through a stochastic, each pass smoothed by half. | real | fastPeriod=23, slowPeriod=50, cyclePeriod=10 | yes |
| [STOCH](functions/stoch.md) | Stochastic (STOCH) | Slow Stochastic oscillator: locates the close within the high-low range over a lookback period, then double-smooths it. | high, low, close | fastK_Period=5, slowK_Period=3, slowK_MAType=SMA (0), slowD_Period=3, slowD_MAType=SMA (0) | yes |
| [STOCHF](functions/stochf.md) | Stochastic Fast (STOCHF) | Fast Stochastic Oscillator: the raw %K line and its moving-average-smoothed %D line. | high, low, close | fastK_Period=5, fastD_Period=3, fastD_MAType=SMA (0) | yes |
| [STOCHRSI](functions/stochrsi.md) | Stochastic Relative Strength Index (STOCHRSI) | Applies the Fast Stochastic (STOCHF) oscillator to an RSI series instead of price, measuring where RSI sits within its recent min/max range. | real | timePeriod=14, fastK_Period=5, fastD_Period=3, fastD_MAType=SMA (0) | yes |
| [TRIX](functions/trix.md) | 1-day Rate-Of-Change (ROC) of a Triple Smooth EMA (TRIX) | 1-day Rate-Of-Change of a triple-smoothed EMA of the input. Momentum oscillator that filters out price moves shorter than the chosen period. | real | timePeriod=30 | yes |
| [TSI](functions/tsi.md) | True Strength Index (TSI) | True Strength Index: William Blau's double-smoothed momentum oscillator. | real | firstPeriod=25, secondPeriod=13 | yes |
| [ULTOSC](functions/ultosc.md) | Ultimate Oscillator (ULTOSC) | Ultimate Oscillator: momentum indicator combining buying-pressure/true-range ratios over three time periods into one 0-100 weighted average. | high, low, close | timePeriod1=7, timePeriod2=14, timePeriod3=28 | yes |
| [VHF](functions/vhf.md) | Vertical Horizontal Filter (VHF) | Vertical Horizontal Filter: Adam White's trend-versus-range filter, the range a window covered divided by the path it actually travelled. Bounded in [0,1]. | real | timePeriod=28 | yes |
| [VORTEX](functions/vortex.md) | Vortex Indicator (VORTEX) | Vortex Indicator: Etienne Botes and Douglas Siepman's two-line trend indicator (Technical Analysis of Stocks & Commodities 28:1, January 2010). | high, low, close | timePeriod=14 | yes |
| [WAD](functions/wad.md) | Williams' Accumulation/Distribution (WAD) | Williams' Accumulation/Distribution: a cumulative line meant to expose whether a security is quietly under accumulation (informed buying) or distribution… | high, low, close | none | yes |
| [WAVETREND](functions/wavetrend.md) | WaveTrend Oscillator (WAVETREND) | WaveTrend Oscillator: how far the typical price sits from its own exponential average, divided by an exponential average of that distance and by… | high, low, close | channelPeriod=10, averagePeriod=21, signalPeriod=4 | yes |
| [WILLR](functions/willr.md) | Williams' %R (WILLR) | Williams' %R momentum oscillator over a rolling period, bounded in [-100, 0]. | high, low, close | timePeriod=14 | yes |

### Overlap Studies

| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python 0.8.3 |
| --- | --- | --- | --- | --- | --- |
| [ACCBANDS](functions/accbands.md) | Acceleration Bands (ACCBANDS) | Acceleration Bands: three overlap lines around price. | high, low, close | timePeriod=20 | yes |
| [ALLIGATOR](functions/alligator.md) | Williams Alligator (ALLIGATOR) | Bill Williams' Alligator (Trading Chaos, 1995): three smoothed moving averages of the median price. | high, low | jawPeriod=13, jawShift=8, teethPeriod=8, teethShift=5, lipsPeriod=5, lipsShift=3 | no |
| [ALMA](functions/alma.md) | Arnaud Legoux Moving Average (ALMA) | Arnaud Legoux Moving Average: the last N inputs weighted by a Gaussian whose peak sits a fraction offset of the way from the oldest to the newest bar. | real | timePeriod=9, sigma=6, offset=0.85 | yes |
| [BBANDS](functions/bbands.md) | Bollinger Bands (BBANDS) | Bollinger Bands: a moving-average middle band with upper and lower bands offset by a multiple of the standard deviation. | real | timePeriod=20, nbDevUp=2, nbDevDn=2, mAType=SMA (0) | yes |
| [CE](functions/ce.md) | Chandelier Exit (CE) | Le Beau's Chandelier Exit, a two-line volatility stop. | high, low, close | timePeriod=22, multiplier=3 | no |
| [CKSP](functions/cksp.md) | Chande Kroll Stop (CKSP) | Chande and Kroll's two-line volatility stop. | high, low, close | timePeriod=10, multiplier=1, stopPeriod=9 | yes |
| [DEMA](functions/dema.md) | Double Exponential Moving Average (DEMA) | Double Exponential Moving Average: an EMA combined with an EMA-of-EMA to reduce lag versus a plain EMA. Overlap Studies overlay on price. | real | timePeriod=30 | yes |
| [DONCHIAN](functions/donchian.md) | Donchian Channels (DONCHIAN) | Donchian Channels: three overlap lines built from rolling price extrema. | high, low | timePeriod=20 | yes |
| [EMA](functions/ema.md) | Exponential Moving Average (EMA) | Exponential moving average that weights recent prices more heavily via a recursive smoothing factor. | real | timePeriod=30 | yes |
| [FRAMA](functions/frama.md) | Fractal Adaptive Moving Average (FRAMA) | Fractal Adaptive Moving Average (John Ehlers): an EMA whose smoothing factor adapts each bar to the fractal dimension of the window, estimated from the… | high, low | timePeriod=16 | yes |
| [HMA](functions/hma.md) | Hull Moving Average (HMA) | Hull Moving Average, published by Alan Hull in 2005: a moving average built to track price with far less lag than an SMA, WMA or EMA of the same length… | real | timePeriod=20 | yes |
| [HT_TRENDLINE](functions/ht_trendline.md) | Hilbert Transform - Instantaneous Trendline (HT_TRENDLINE) | Ehlers' Hilbert Transform Instantaneous Trendline: a smoothed, low-lag overlay whose averaging window adapts to the dominant cycle period measured via… | real | none | yes |
| [ICHIMOKU](functions/ichimoku.md) | Ichimoku Kinko Hyo (ICHIMOKU) | Ichimoku Kinko Hyo, "one glance equilibrium chart": four lines built from highs and lows alone. | high, low | tenkanPeriod=9, kijunPeriod=26, senkouBPeriod=52 | yes |
| [KAMA](functions/kama.md) | Kaufman Adaptive Moving Average (KAMA) | Kaufman Adaptive Moving Average: an EMA whose smoothing factor adapts each bar to an efficiency ratio (directional move vs. total volatility). | real | timePeriod=30 | yes |
| [KC](functions/kc.md) | Keltner Channels (KC) | Keltner Channels: three overlap lines around price. | high, low, close | timePeriod=20, aTRPeriod=10, nbDev=2 | yes |
| [MA](functions/ma.md) | Moving average (MA) | Generic moving-average dispatcher that forwards the job to the MA implementation selected by optInMAType. | real | timePeriod=30, mAType=SMA (0) | yes |
| [MAENV](functions/maenv.md) | Moving Average Envelope (MAENV) | Moving Average Envelope: a moving average with one band a fixed percentage above it and one a fixed percentage below. | real | timePeriod=20, percentUp=10, percentDn=10, mAType=SMA (0) | no |
| [MAMA](functions/mama.md) | MESA Adaptive Moving Average (MAMA) | MESA Adaptive Moving Average: an adaptive EMA whose smoothing factor is driven by the dominant-cycle phase rate measured with a Hilbert transform. | real | fastLimit=0.5, slowLimit=0.05 | yes |
| [MAVP](functions/mavp.md) | Moving average with variable period (MAVP) | Moving average whose period varies per bar, driven by a companion period series. | real, periods | minPeriod=2, maxPeriod=30, mAType=SMA (0) | yes |
| [MCGD](functions/mcgd.md) | McGinley Dynamic (MCGD) | McGinley Dynamic (John R. McGinley, Jr.): a moving average whose speed adjusts to the market. | real | timePeriod=14 | yes |
| [MIDPOINT](functions/midpoint.md) | MidPoint over period (MIDPOINT) | Midpoint over a period: the average of the highest and lowest input values within the lookback window. | real | timePeriod=14 | yes |
| [MIDPRICE](functions/midprice.md) | Midpoint Price over period (MIDPRICE) | Midpoint of the price range over a rolling window: the average of the highest high and lowest low across the last optInTimePeriod bars. | high, low | timePeriod=14 | yes |
| [RMA](functions/rma.md) | Wilder's Smoothed Moving Average (RMA) | Wilder's smoothed moving average: an exponential average whose smoothing factor is the reciprocal of the period rather than the 2/(n+1) of a classic EMA… | real | timePeriod=30 | yes |
| [SAR](functions/sar.md) | Parabolic SAR (SAR) | Wilder's Parabolic SAR (Stop And Reverse): a trailing stop/reverse level that accelerates toward price via an acceleration factor. | high, low | acceleration=0.02, maximum=0.2 | yes |
| [SAREXT](functions/sarext.md) | Parabolic SAR - Extended (SAREXT) | Extended Parabolic SAR (stop and reverse) giving the caller full control over the initial state and separate acceleration factors for long and short… | high, low | startValue=0, offsetOnReverse=0, accelerationInitLong=0.02, accelerationLong=0.02, accelerationMaxLong=0.2, accelerationInitShort=0.02, accelerationShort=0.02, accelerationMaxShort=0.2 | yes |
| [SMA](functions/sma.md) | Simple Moving Average (SMA) | Simple Moving Average: the unweighted arithmetic mean of the last N input values. Used to smooth a series. | real | timePeriod=30 | yes |
| [SSF](functions/ssf.md) | Ehlers SuperSmoother Filter (SSF) | John Ehlers' SuperSmoother: a two-pole low-pass smoother with a zero at Nyquist, which he recommends for use instead of an EMA and builds most of his… | real | timePeriod=10 | no |
| [SUPERTREND](functions/supertrend.md) | SuperTrend (SUPERTREND) | An ATR-scaled trailing band that follows price on one side at a time and flips to the other side when the close breaks through it. | high, low, close | timePeriod=10, multiplier=3 | yes |
| [SWAK_BUTTER](functions/swak_butter.md) | Swiss Army Knife - Butterworth Filter (SWAK_BUTTER) | The Butterworth row of John Ehlers' Swiss Army Knife filter: the Gaussian row's double real pole with two zeros added at Nyquist, giving a two-pole… | real | timePeriod=20 | yes |
| [SWAK_GAUSS](functions/swak_gauss.md) | Swiss Army Knife - Gaussian Filter (SWAK_GAUSS) | The Gaussian row of John Ehlers' Swiss Army Knife filter: a two-pole low-pass smoother whose impulse response approximates a Gaussian, so it lags price… | real | timePeriod=20 | yes |
| [T3](functions/t3.md) | Triple Exponential Moving Average (T3) (T3) | Tillson's T3: a low-lag moving average built from six chained EMAs, combined via volume-factor-weighted coefficients. | real | timePeriod=5, vFactor=0.7 | yes |
| [TEMA](functions/tema.md) | Triple Exponential Moving Average (TEMA) | Triple Exponential Moving Average: a smoothed price overlay built from three successively-applied EMAs to reduce lag versus a plain EMA. | real | timePeriod=30 | yes |
| [TRIMA](functions/trima.md) | Triangular Moving Average (TRIMA) | Triangular Moving Average: a double-smoothed moving average that weights prices toward the middle of the window most heavily. | real | timePeriod=30 | yes |
| [VIDYA](functions/vidya.md) | Variable Index Dynamic Average (VIDYA) | Variable Index Dynamic Average (Tushar Chande): an EMA whose smoothing factor is scaled every bar by the absolute value of the Chande Momentum Oscillator. | real | timePeriod=12, cMOPeriod=9 | yes |
| [VWMA](functions/vwma.md) | Volume Weighted Moving Average (VWMA) | Volume Weighted Moving Average: the mean price over a trailing window of optInTimePeriod bars, each bar weighted by its own volume. | real, volume | timePeriod=30 | yes |
| [WMA](functions/wma.md) | Weighted Moving Average (WMA) | Linearly weighted moving average: each of the last N prices is weighted by its position, oldest getting weight 1 and newest weight N. | real | timePeriod=30 | yes |
| [ZIGZAG](functions/zigzag.md) | Zig Zag (ZIGZAG) | The percent-filter swing line. | high, low | sensitivity=5, minTrendLength=1 | yes |
| [ZLEMA](functions/zlema.md) | Zero-Lag Exponential Moving Average (ZLEMA) | Zero-Lag Exponential Moving Average: an EMA applied not to price but to a de-lagged series that extrapolates price forward by the EMA's own lag… | real | timePeriod=30 | yes |

### Pattern Recognition

| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python 0.8.3 |
| --- | --- | --- | --- | --- | --- |
| [CDL2CROWS](functions/cdl2crows.md) | Two Crows (CDL2CROWS) | Three-candle bearish reversal pattern: a long white candle, then a black candle gapping up, then a black candle that opens inside the second body and… | open, high, low, close | none | yes |
| [CDL3BLACKCROWS](functions/cdl3blackcrows.md) | Three Black Crows (CDL3BLACKCROWS) | A four-bar pattern: a white candle followed by three consecutive black (down) candles with successively lower closes, each opening inside the prior… | open, high, low, close | none | yes |
| [CDL3INSIDE](functions/cdl3inside.md) | Three Inside Up/Down (CDL3INSIDE) | A three-candle reversal pattern: a long real body, then a short real body totally engulfed by it (a harami), then a third candle of opposite color to the… | open, high, low, close | none | yes |
| [CDL3LINESTRIKE](functions/cdl3linestrike.md) | Three-Line Strike (CDL3LINESTRIKE) | A four-candle pattern: three same-color candles with consecutively higher (or lower) closes, each opening within or near the prior real body, then a… | open, high, low, close | none | yes |
| [CDL3OUTSIDE](functions/cdl3outside.md) | Three Outside Up/Down (CDL3OUTSIDE) | A three-candle pattern: an engulfing pair (candle 2's body fully engulfs candle 1's body) followed by a third candle that confirms in the engulfing… | open, high, low, close | none | yes |
| [CDL3STARSINSOUTH](functions/cdl3starsinsouth.md) | Three Stars In The South (CDL3STARSINSOUTH) | A three-candle bullish reversal pattern of three consecutive black candles that progressively shrink and stabilize: a long black candle with a long lower… | open, high, low, close | none | yes |
| [CDL3WHITESOLDIERS](functions/cdl3whitesoldiers.md) | Three Advancing White Soldiers (CDL3WHITESOLDIERS) | A three-candle pattern of consecutive white candles with progressively higher closes, each opening within/near the prior body and each with a very short… | open, high, low, close | none | yes |
| [CDLABANDONEDBABY](functions/cdlabandonedbaby.md) | Abandoned Baby (CDLABANDONEDBABY) | A three-candle reversal pattern: a long body, then a gapped-away doji, then a body of opposite color that gaps back the other way and closes deep into… | open, high, low, close | penetration=0.3 | yes |
| [CDLADVANCEBLOCK](functions/cdladvanceblock.md) | Advance Block (CDLADVANCEBLOCK) | Three-candle bearish reversal pattern: three white candles with consecutively higher closes whose advance weakens (progressively smaller bodies and/or… | open, high, low, close | none | yes |
| [CDLBELTHOLD](functions/cdlbelthold.md) | Belt-hold (CDLBELTHOLD) | Single-candle pattern with a long real body that opens at (or near) its extreme. | open, high, low, close | none | yes |
| [CDLBREAKAWAY](functions/cdlbreakaway.md) | Breakaway (CDLBREAKAWAY) | A five-candle reversal pattern: a long first candle, a same-colored second candle that gaps away from it by its real body, two more candles extending the… | open, high, low, close | none | yes |
| [CDLCLOSINGMARUBOZU](functions/cdlclosingmarubozu.md) | Closing Marubozu (CDLCLOSINGMARUBOZU) | Single-candle pattern: a long real body whose closing end has no or very short shadow, so the close sits at the candle's extreme. | open, high, low, close | none | yes |
| [CDLCONCEALBABYSWALL](functions/cdlconcealbabyswall.md) | Concealing Baby Swallow (CDLCONCEALBABYSWALL) | A four-candle pattern: two black marubozus, then a black candle that gaps down but pokes its upper shadow into the prior body, then a larger black candle… | open, high, low, close | none | yes |
| [CDLCOUNTERATTACK](functions/cdlcounterattack.md) | Counterattack (CDLCOUNTERATTACK) | A two-candle pattern of two long, opposite-colored real bodies whose closing prices are (nearly) equal. | open, high, low, close | none | yes |
| [CDLDARKCLOUDCOVER](functions/cdldarkcloudcover.md) | Dark Cloud Cover (CDLDARKCLOUDCOVER) | A two-candle bearish reversal pattern: a long white candle followed by a black candle that opens above the prior high and closes deep into the prior… | open, high, low, close | penetration=0.5 | yes |
| [CDLDOJI](functions/cdldoji.md) | Doji (CDLDOJI) | Single-candle Doji recognizer: fires when the real body (\|close-open\|) is at or below the BodyDoji threshold. | open, high, low, close | none | yes |
| [CDLDOJISTAR](functions/cdldojistar.md) | Doji Star (CDLDOJISTAR) | A two-candle reversal pattern: a long real body followed by a doji whose real body gaps away from it (up after a white body, down after a black body). | open, high, low, close | none | yes |
| [CDLDRAGONFLYDOJI](functions/cdldragonflydoji.md) | Dragonfly Doji (CDLDRAGONFLYDOJI) | Single-candle pattern: a doji (open and close nearly equal) sitting at the top of the range, with no meaningful upper shadow and a long lower shadow. | open, high, low, close | none | yes |
| [CDLENGULFING](functions/cdlengulfing.md) | Engulfing Pattern (CDLENGULFING) | A two-candle reversal pattern where the second candle's real body engulfs the first candle's opposite-colored real body. | open, high, low, close | none | yes |
| [CDLEVENINGDOJISTAR](functions/cdleveningdojistar.md) | Evening Doji Star (CDLEVENINGDOJISTAR) | A three-candle bearish reversal pattern: a long white candle, a doji that gaps up (the star), then a black candle closing well down into the first… | open, high, low, close | penetration=0.3 | yes |
| [CDLEVENINGSTAR](functions/cdleveningstar.md) | Evening Star (CDLEVENINGSTAR) | A three-candle bearish reversal pattern: a long white candle, a short-bodied star gapping up, then a black candle closing well down into the first… | open, high, low, close | penetration=0.3 | yes |
| [CDLGAPSIDESIDEWHITE](functions/cdlgapsidesidewhite.md) | Up/Down-gap side-by-side white lines (CDLGAPSIDESIDEWHITE) | A three-candle pattern: a first candle followed by two white candles of similar body size that both gap the same direction (up or down) from the first… | open, high, low, close | none | yes |
| [CDLGRAVESTONEDOJI](functions/cdlgravestonedoji.md) | Gravestone Doji (CDLGRAVESTONEDOJI) | Single-candle doji whose open and close sit at the low of the day, leaving a long upper shadow and no lower shadow. | open, high, low, close | none | yes |
| [CDLHAMMER](functions/cdlhammer.md) | Hammer (CDLHAMMER) | Single-candle pattern: a small real body at the top of the range with a long lower shadow and little or no upper shadow, sitting at or near the prior… | open, high, low, close | none | yes |
| [CDLHANGINGMAN](functions/cdlhangingman.md) | Hanging Man (CDLHANGINGMAN) | Single candle with a small real body, a long lower shadow, and little/no upper shadow, sitting at or near the highs of the prior candle. | open, high, low, close | none | yes |
| [CDLHARAMI](functions/cdlharami.md) | Harami Pattern (CDLHARAMI) | Two-candle pattern: a long real body followed by a short real body contained within the first candle's real body. | open, high, low, close | none | yes |
| [CDLHARAMICROSS](functions/cdlharamicross.md) | Harami Cross Pattern (CDLHARAMICROSS) | A two-candle reversal pattern: a long real body followed by a doji whose real body is contained within the first candle's real body (the doji variant of… | open, high, low, close | none | yes |
| [CDLHIGHWAVE](functions/cdlhighwave.md) | High-Wave Candle (CDLHIGHWAVE) | Single-candle pattern: a short real body with both a very long upper and a very long lower shadow. | open, high, low, close | none | yes |
| [CDLHIKKAKE](functions/cdlhikkake.md) | Hikkake Pattern (CDLHIKKAKE) | A 3-bar pattern: an inside bar followed by a false breakout, optionally later confirmed by a follow-through bar. | open, high, low, close | none | yes |
| [CDLHIKKAKEMOD](functions/cdlhikkakemod.md) | Modified Hikkake Pattern (CDLHIKKAKEMOD) | A four-candle pattern: two successively narrower inside bars, then a breakout bar, with the second candle closing near one extreme of its range. | open, high, low, close | none | yes |
| [CDLHOMINGPIGEON](functions/cdlhomingpigeon.md) | Homing Pigeon (CDLHOMINGPIGEON) | Two-candle pattern: a long black candle followed by a small black candle whose real body sits inside the prior body. | open, high, low, close | none | yes |
| [CDLIDENTICAL3CROWS](functions/cdlidentical3crows.md) | Identical Three Crows (CDLIDENTICAL3CROWS) | A three-candle bearish reversal pattern: three consecutive declining black candles, each with a very short (or no) lower shadow, where each candle after… | open, high, low, close | none | yes |
| [CDLINNECK](functions/cdlinneck.md) | In-Neck Pattern (CDLINNECK) | A two-candle in-neck pattern: a long black candle followed by a white candle that opens below the prior low and closes just barely into the prior body… | open, high, low, close | none | yes |
| [CDLINVERTEDHAMMER](functions/cdlinvertedhammer.md) | Inverted Hammer (CDLINVERTEDHAMMER) | Single-candle pattern: a small real body with a long upper shadow and little-to-no lower shadow that gaps down from the prior candle. | open, high, low, close | none | yes |
| [CDLKICKING](functions/cdlkicking.md) | Kicking (CDLKICKING) | Two-candle pattern of two opposite-color marubozu (long bodies with very short shadows) separated by a price gap. | open, high, low, close | none | yes |
| [CDLKICKINGBYLENGTH](functions/cdlkickingbylength.md) | Kicking - bull/bear determined by the longer marubozu (CDLKICKINGBYLENGTH) | A two-candle pattern of two opposite-color marubozu (long body, very short shadows on both ends) separated by a gap. | open, high, low, close | none | yes |
| [CDLLADDERBOTTOM](functions/cdlladderbottom.md) | Ladder Bottom (CDLLADDERBOTTOM) | Five-candle bullish reversal pattern: three consecutively lower black candles, a fourth black candle with a non-very-short upper shadow, then a white… | open, high, low, close | none | yes |
| [CDLLONGLEGGEDDOJI](functions/cdllongleggeddoji.md) | Long Legged Doji (CDLLONGLEGGEDDOJI) | Single-candle doji (open ~ close) with at least one long shadow. Signals market indecision, not a directional bias. | open, high, low, close | none | yes |
| [CDLLONGLINE](functions/cdllongline.md) | Long Line Candle (CDLLONGLINE) | A single-candle pattern: a long real body with short upper and short lower shadow. | open, high, low, close | none | yes |
| [CDLMARUBOZU](functions/cdlmarubozu.md) | Marubozu (CDLMARUBOZU) | Single candle with a long real body and no/very-short upper and lower shadows, so open and close sit at the range extremes. | open, high, low, close | none | yes |
| [CDLMATCHINGLOW](functions/cdlmatchinglow.md) | Matching Low (CDLMATCHINGLOW) | A two-candle pattern of two consecutive black (bearish) candles with equal closes (within a tolerance). Treated as a bullish reversal signal. | open, high, low, close | none | yes |
| [CDLMATHOLD](functions/cdlmathold.md) | Mat Hold (CDLMATHOLD) | A five-candle bullish continuation pattern: a long white candle, an upside real-body-gapped small black candle, two more small falling candles that hold… | open, high, low, close | penetration=0.5 | yes |
| [CDLMORNINGDOJISTAR](functions/cdlmorningdojistar.md) | Morning Doji Star (CDLMORNINGDOJISTAR) | A three-candle bullish reversal pattern: a long black candle, then a doji that gaps down, then a white candle closing well up into the first candle's body. | open, high, low, close | penetration=0.3 | yes |
| [CDLMORNINGSTAR](functions/cdlmorningstar.md) | Morning Star (CDLMORNINGSTAR) | A three-candle bottom-reversal pattern: a long black candle, a small-bodied star gapping down, then a white candle closing well up into the first… | open, high, low, close | penetration=0.3 | yes |
| [CDLONNECK](functions/cdlonneck.md) | On-Neck Pattern (CDLONNECK) | A two-candle on-neck pattern: a long black candle followed by a white candle that opens below the prior candle's low and closes right at that low. | open, high, low, close | none | yes |
| [CDLPIERCING](functions/cdlpiercing.md) | Piercing Pattern (CDLPIERCING) | Two-candle pattern: a long black candle followed by a long white candle that opens below the prior low and closes back above the midpoint of the prior… | open, high, low, close | none | yes |
| [CDLRICKSHAWMAN](functions/cdlrickshawman.md) | Rickshaw Man (CDLRICKSHAWMAN) | Single-candle doji with two long shadows whose body sits near the midpoint of the high-low range. | open, high, low, close | none | yes |
| [CDLRISEFALL3METHODS](functions/cdlrisefall3methods.md) | Rising/Falling Three Methods (CDLRISEFALL3METHODS) | A five-candle continuation pattern: a long candle, three small counter-color candles that stay partly within the first candle's high-low range, then a… | open, high, low, close | none | yes |
| [CDLSEPARATINGLINES](functions/cdlseparatinglines.md) | Separating Lines (CDLSEPARATINGLINES) | A two-candle continuation pattern: the second candle opposes the first in color, opens at the same price as the first, and is a long-bodied belt hold. | open, high, low, close | none | yes |
| [CDLSHOOTINGSTAR](functions/cdlshootingstar.md) | Shooting Star (CDLSHOOTINGSTAR) | Single-candle pattern: a small real body with a long upper shadow and little-to-no lower shadow that gaps up from the prior candle's real body. | open, high, low, close | none | yes |
| [CDLSHORTLINE](functions/cdlshortline.md) | Short Line Candle (CDLSHORTLINE) | Single-candle pattern: a short real body with short upper and lower shadows (a small-range candle). | open, high, low, close | none | yes |
| [CDLSPINNINGTOP](functions/cdlspinningtop.md) | Spinning Top (CDLSPINNINGTOP) | Single-candle pattern: a small real body with both an upper and a lower shadow longer than the body. | open, high, low, close | none | yes |
| [CDLSTALLEDPATTERN](functions/cdlstalledpattern.md) | Stalled Pattern (CDLSTALLEDPATTERN) | A three-candle pattern of three white candles with consecutively higher closes where the third loses momentum (a small body riding on the shoulder of the… | open, high, low, close | none | yes |
| [CDLSTICKSANDWICH](functions/cdlsticksandwich.md) | Stick Sandwich (CDLSTICKSANDWICH) | A three-candle bullish reversal pattern: two black candles (1st and 3rd) sandwiching a white candle, where the 3rd black candle closes at the same level… | open, high, low, close | none | yes |
| [CDLTAKURI](functions/cdltakuri.md) | Takuri (Dragonfly Doji with very long lower shadow) (CDLTAKURI) | Single-candle pattern: a doji whose open and close sit at the high (no/very short upper shadow) with a very long lower shadow, i.e. a dragonfly doji with… | open, high, low, close | none | yes |
| [CDLTASUKIGAP](functions/cdltasukigap.md) | Tasuki Gap (CDLTASUKIGAP) | A three-candle pattern: a real-body-gapping candle followed by an opposite-color candle that opens inside its body and closes back into the gap without… | open, high, low, close | none | yes |
| [CDLTHRUSTING](functions/cdlthrusting.md) | Thrusting Pattern (CDLTHRUSTING) | A two-candle pattern: a long black candle followed by a white candle that opens below the prior low and closes back into the prior body but below its… | open, high, low, close | none | yes |
| [CDLTRISTAR](functions/cdltristar.md) | Tristar Pattern (CDLTRISTAR) | A three-candle pattern of three consecutive doji where the middle doji is a star (its body gaps away from the first). Bullish or bearish reversal signal. | open, high, low, close | none | yes |
| [CDLUNIQUE3RIVER](functions/cdlunique3river.md) | Unique 3 River (CDLUNIQUE3RIVER) | A three-candle bullish reversal pattern: a long black candle, then a black harami candle that makes a lower low, then a small white candle. | open, high, low, close | none | yes |
| [CDLUPSIDEGAP2CROWS](functions/cdlupsidegap2crows.md) | Upside Gap Two Crows (CDLUPSIDEGAP2CROWS) | A three-candle bearish reversal pattern: a long white candle, then a small black candle gapping up (a gap between the real bodies), then a black candle… | open, high, low, close | none | yes |
| [CDLXSIDEGAP3METHODS](functions/cdlxsidegap3methods.md) | Upside/Downside Gap Three Methods (CDLXSIDEGAP3METHODS) | A three-candle continuation pattern: two same-color candles separated by a real-body gap, followed by an opposite-color candle that fills into the gap. | open, high, low, close | none | yes |

### Price Transform

| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python 0.8.3 |
| --- | --- | --- | --- | --- | --- |
| [AVGDEV](functions/avgdev.md) | Average Deviation (AVGDEV) | Rolling average absolute deviation of a series from its own simple moving average over the last N periods. Measures dispersion around the window mean. | real | timePeriod=14 | yes |
| [AVGPRICE](functions/avgprice.md) | Average Price (AVGPRICE) | Average Price: the arithmetic mean of each bar's open, high, low, and close. A price-transform overlap condensing OHLC into a single representative price. | open, high, low, close | none | yes |
| [HA](functions/ha.md) | Heikin-Ashi Candles (HA) | Heikin-Ashi candles: an OHLC-to-OHLC transform that replaces each bar with a smoothed synthetic candle. | open, high, low, close | none | yes |
| [MEDPRICE](functions/medprice.md) | Median Price (MEDPRICE) | Median Price: the midpoint of each bar's high and low. A price-transform overlay. | high, low | none | yes |
| [TYPPRICE](functions/typprice.md) | Typical Price (TYPPRICE) | Typical Price: the average of the high, low, and close of each bar. A single representative price per period. | high, low, close | none | yes |
| [WCLPRICE](functions/wclprice.md) | Weighted Close Price (WCLPRICE) | Weighted Close Price: a per-bar price average giving the close double weight relative to high and low. | high, low, close | none | yes |

### Statistic Functions

| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python 0.8.3 |
| --- | --- | --- | --- | --- | --- |
| [BETA](functions/beta.md) | Beta (BETA) | Beta: the slope of a least-squares linear regression of one series' percentage returns (y, from inReal1) against another's (x, from inReal0) over a… | real0, real1 | timePeriod=5 | yes |
| [CORREL](functions/correl.md) | Pearson's Correlation Coefficient (r) (CORREL) | Pearson's correlation coefficient (r) between two input series over a rolling window of optInTimePeriod bars. | real0, real1 | timePeriod=30 | yes |
| [KURTOSIS](functions/kurtosis.md) | Rolling Excess Kurtosis (KURTOSIS) | An estimate, from the trailing window, of the excess kurtosis of the distribution its values come from: the fourth standardised moment minus 3, so a… | real | timePeriod=30 | yes |
| [LINEARREG](functions/linearreg.md) | Linear Regression (LINEARREG) | Least-squares straight-line fit over the last optInTimePeriod bars, reported as the fitted line value at the window endpoint (b + m*(period-1)). | real | timePeriod=14 | yes |
| [LINEARREG_ANGLE](functions/linearreg_angle.md) | Linear Regression Angle (LINEARREG_ANGLE) | The angle, in degrees, of the least-squares best-fit line over the last N points. | real | timePeriod=14 | yes |
| [LINEARREG_INTERCEPT](functions/linearreg_intercept.md) | Linear Regression Intercept (LINEARREG_INTERCEPT) | Returns the y-intercept (b) of the least-squares regression line fitted over the last optInTimePeriod values. | real | timePeriod=14 | yes |
| [LINEARREG_SLOPE](functions/linearreg_slope.md) | Linear Regression Slope (LINEARREG_SLOPE) | Slope 'm' of the least-squares best-fit line (y = b + m*x) over the last optInTimePeriod bars. Reports the per-bar rate of change of the fitted trend line. | real | timePeriod=14 | yes |
| [MEDIAN](functions/median.md) | Rolling Median (MEDIAN) | The middle order statistic of the trailing window: the central value when optInTimePeriod is odd, the mean of the two central values when it is even. | real | timePeriod=30 | yes |
| [PERCENTILE](functions/percentile.md) | Percentile (nearest rank) (PERCENTILE) | Rolling percentile by the nearest-rank method: sort the trailing window ascending and report the value whose 1-based ordinal rank is the P-th percentile… | real | timePeriod=100, percentile=50 | yes |
| [PERCENTRANK](functions/percentrank.md) | Percent Rank (PERCENTRANK) | Percent Rank: where the current value sits inside the distribution of the values that came before it, as a percentage. | real | timePeriod=100 | yes |
| [SHARPE](functions/sharpe.md) | Rolling Sharpe Ratio (SHARPE) | The rolling Sharpe ratio: the mean return in excess of a risk-free rate, divided by the standard deviation of that excess return, over a trailing window. | real | timePeriod=20, riskFreeRate=0, annualization=252 | no |
| [SKEW](functions/skew.md) | Rolling Skewness (SKEW) | An estimate, from the trailing window, of the skewness of the distribution its values come from: the third standardised moment. | real | timePeriod=30 | no |
| [SORTINO](functions/sortino.md) | Rolling Sortino Ratio (SORTINO) | The rolling Sortino ratio: the mean return in excess of a minimum acceptable return (MAR), divided by the downside deviation, over a trailing window… | real | timePeriod=20, mAR=0, annualization=252 | no |
| [STDDEV](functions/stddev.md) | Standard Deviation (STDDEV) | Rolling standard deviation of a series over a window, scaled by a deviations multiplier. Delegates to VAR, then takes the square root. | real | timePeriod=5, nbDev=1 | yes |
| [TSF](functions/tsf.md) | Time Series Forecast (TSF) | Time Series Forecast: fits a least-squares linear regression line over the last N bars and projects it one x-step beyond LINEARREG. | real | timePeriod=14 | yes |
| [VAR](functions/var.md) | Variance (VAR) | Rolling population variance of a real series over a given period. Measures dispersion of values around their mean. | real | timePeriod=5, nbDev=1 | yes |

### Volatility Indicators

| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python 0.8.3 |
| --- | --- | --- | --- | --- | --- |
| [ADR](functions/adr.md) | Average Day Range (ADR) | Average Day Range: the arithmetic mean of the last optInTimePeriod bar ranges, high minus low. | high, low | timePeriod=14 | yes |
| [ATR](functions/atr.md) | Average True Range (ATR) | Wilder-smoothed average of the True Range over a period, measuring price volatility regardless of direction. | high, low, close | timePeriod=14 | yes |
| [BBW](functions/bbw.md) | Bollinger BandWidth (BBW) | Bollinger BandWidth: the distance between the upper and lower Bollinger Bands as a percentage of the middle band. | real | timePeriod=20, nbDevUp=2, nbDevDn=2, mAType=SMA (0) | yes |
| [CVI](functions/cvi.md) | Chaikin's Volatility (CVI) | Chaikin's Volatility: Marc Chaikin's reading of how fast a market's daily trading range is widening or narrowing. | high, low | timePeriod=10, rOCPeriod=10 | yes |
| [MASSI](functions/massi.md) | Mass Index (MASSI) | Mass Index: Donald Dorsey's non-directional measure of how the trading range itself is expanding or contracting. | high, low | fastPeriod=9, slowPeriod=25 | yes |
| [NATR](functions/natr.md) | Normalized Average True Range (NATR) | Average True Range expressed as a percentage of the current close, making volatility comparable across price levels and securities. | high, low, close | timePeriod=14 | yes |
| [PERCENTB](functions/percentb.md) | Bollinger Bands %B (PERCENTB) | Bollinger Bands %B: where the input sits relative to its Bollinger Bands, 0 at the lower band and 1 at the upper band. | real | timePeriod=20, nbDevUp=2, nbDevDn=2, mAType=SMA (0) | yes |
| [ROGERSSATCHELL](functions/rogerssatchell.md) | Rogers-Satchell Volatility (ROGERSSATCHELL) | Rogers-Satchell volatility: a range-based estimator that reads one bar's open, high, low and close as a single unbiased estimate of that bar's variance… | open, high, low, close | timePeriod=10, annualization=252 | yes |
| [RVI](functions/rvi.md) | Relative Volatility Index (RVI) | Relative Volatility Index: Donald Dorsey's volatility oscillator, built exactly like RSI except that the quantity routed to the up and down buckets is… | real | timePeriod=14, stdDevPeriod=10 | yes |
| [RVIR](functions/rvir.md) | Relative Volatility Index, refined high/low form (RVIR) | Relative Volatility Index, refined form: Donald Dorsey's 1995 revision of his own indicator, which runs the 1993 RVI over the daily highs and again over… | high, low | timePeriod=14, stdDevPeriod=10 | yes |
| [TRANGE](functions/trange.md) | True Range (TRANGE) | True Range: the greatest of today's high-low span and the two gaps between yesterday's close and today's high/low. | high, low, close | none | yes |

### Volume Indicators

| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python 0.8.3 |
| --- | --- | --- | --- | --- | --- |
| [AD](functions/ad.md) | Chaikin A/D Line (AD) | Chaikin Accumulation/Distribution Line, a cumulative volume-flow indicator. | high, low, close, volume | none | yes |
| [ADOSC](functions/adosc.md) | Chaikin A/D Oscillator (ADOSC) | Chaikin A/D Oscillator: the difference between a fast and a slow EMA of the Accumulation/Distribution line. | high, low, close, volume | fastPeriod=3, slowPeriod=10 | yes |
| [CMF](functions/cmf.md) | Chaikin Money Flow (CMF) | Chaikin Money Flow: over a trailing window of optInTimePeriod bars, the sum of each bar's money flow volume divided by the sum of its volume. | high, low, close, volume | timePeriod=20 | yes |
| [EFI](functions/efi.md) | Elder's Force Index (EFI) | Alexander Elder's Force Index (Trading for a Living, 1993): volume-weighted momentum. | close, volume | timePeriod=13 | yes |
| [EMV](functions/emv.md) | Arms Ease of Movement (EMV) | Ease of Movement: the bar-to-bar move of the high-low midpoint divided by a box ratio of volume to range, averaged over a trailing window. | high, low, volume | timePeriod=14, volumeDivisor=10000 | yes |
| [KVO](functions/kvo.md) | Klinger Volume Oscillator (KVO) | Klinger Volume Oscillator: each bar's volume is signed by the direction of its high-low-close sum and weighted by where the bar's own range sits inside… | high, low, close, volume | fastPeriod=34, slowPeriod=55, signalPeriod=13 | yes |
| [MARKETFI](functions/marketfi.md) | Market Facilitation Index (MARKETFI) | Bill Williams' Market Facilitation Index (Trading Chaos, 1995): the price range a bar travelled per unit of volume traded — how much movement the market… | high, low, volume | none | yes |
| [NVI](functions/nvi.md) | Negative Volume Index (NVI) | Negative Volume Index: a running cumulative index that changes only on days when volume falls versus the prior day, compounding that day's percentage… | close, volume | none | yes |
| [OBV](functions/obv.md) | On Balance Volume (OBV) | On Balance Volume: a running cumulative total of volume, added on up-price bars and subtracted on down-price bars. Relates volume flow to price direction. | real, volume | none | yes |
| [PVI](functions/pvi.md) | Positive Volume Index (PVI) | Positive Volume Index: a running cumulative index that changes only on days when volume rises versus the prior day, compounding that day's percentage… | close, volume | none | yes |
| [PVO](functions/pvo.md) | Percentage Volume Oscillator (PVO) | Percentage Volume Oscillator: a variation of the Percentage Price Oscillator (PPO, created by Gerald Appel) applied to the volume series instead of price. | volume | fastPeriod=12, slowPeriod=26, mAType=EMA (1) | yes |
| [PVT](functions/pvt.md) | Price Volume Trend (PVT) | Price Volume Trend: a running cumulative total of each bar's volume weighted by that bar's fractional price change. | close, volume | none | yes |
| [RVOL](functions/rvol.md) | Relative Volume (RVOL) | Relative Volume: today's volume as a ratio to the average volume of the bars that came before it. | volume | timePeriod=20 | yes |
| [VWAP](functions/vwap.md) | Volume Weighted Average Price (VWAP) | Volume Weighted Average Price: the average price paid per unit of volume traded, accumulated from the first bar of the range onward. | high, low, close, volume | none | yes |
