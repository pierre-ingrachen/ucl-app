# IA-optimisee : resultats (walk-forward, hors echantillon)

Candidats evalues : 13839 (victoire dom./ext. a cote moyenne >= 3.3, saisons 2021-22 a 2026-27).

Log-loss de P(victoire) sur ce segment : modele 0.4498 | taux de base constant 0.4587 | 1/cote moyenne du marche (non normalisee) 0.4435.


## Hypothese de cote : Bet365 cloture

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 (marge 5%, plafond 6.0) | 264 | 38 | 51.6 | -13.6 | -26.3% | [-48% ; -3%] | 17.3 |
| 2024-25 (marge 40%, plafond 12.0) | 74 | 2 | 8.5 | -6.5 | -76.4% | [-100% ; -40%] | 7.1 |
| 2025-26 (marge 5%, plafond 6.0) | 189 | 32 | 36.8 | -4.8 | -13.0% | [-40% ; +15%] | 8.0 |
| 2026-27 (marge 0%, plafond 6.0) | 106 | 23 | 20.5 | 2.5 | +12.3% | [-27% ; +52%] | 3.6 |
| **TOTAL regle choisie sur le passe** | 633 | 95 | 117.3 | -22.3 | -19.0% | [-34% ; -4%] | 29.5 |
| Pari a l'aveugle (cote > 4) | 6112 | 816 | 1016.3 | -200.3 | -19.7% | [-25% ; -15%] | 205.1 |
| Regle fixe : marge 0%, sans plafond | 2531 | 291 | 363.9 | -72.9 | -20.0% | [-28% ; -11%] | 75.3 |
| Regle fixe : marge 10%, sans plafond | 1650 | 152 | 214.4 | -62.4 | -29.1% | [-39% ; -18%] | 63.5 |
| Regle fixe : marge 20%, sans plafond | 1117 | 84 | 133.2 | -49.2 | -36.9% | [-49% ; -24%] | 49.3 |


## Hypothese de cote : Bet365 cloture -5%

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 (marge 0%, plafond 6.0) | 230 | 35 | 46.4 | -11.4 | -24.6% | [-46% ; -1%] | 14.9 |
| 2024-25 (marge 30%, plafond 8.0) | 41 | 1 | 5.8 | -4.8 | -82.7% | [-100% ; -46%] | 4.6 |
| 2025-26 (marge 0%, plafond 6.0) | 196 | 33 | 38.6 | -5.6 | -14.4% | [-41% ; +14%] | 8.7 |
| 2026-27 (marge 0%, plafond 6.0) | 73 | 17 | 13.9 | 3.1 | +22.0% | [-28% ; +73%] | 2.3 |
| **TOTAL regle choisie sur le passe** | 540 | 86 | 104.7 | -18.7 | -17.8% | [-33% ; -1%] | 25.0 |
| Pari a l'aveugle (cote > 4) | 5559 | 714 | 934.4 | -220.4 | -23.6% | [-29% ; -18%] | 224.4 |
| Regle fixe : marge 0%, sans plafond | 1955 | 196 | 276.8 | -80.8 | -29.2% | [-38% ; -20%] | 82.3 |
| Regle fixe : marge 10%, sans plafond | 1265 | 104 | 162.7 | -58.7 | -36.1% | [-48% ; -24%] | 59.4 |
| Regle fixe : marge 20%, sans plafond | 812 | 56 | 94.6 | -38.6 | -40.8% | [-55% ; -25%] | 39.0 |


Regle choisie, par issue (Bet365 cloture -5%) :

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| dom | 140 | 19 | 27.0 | -8.0 | -29.5% | [-59% ; +1%] | 10.9 |
| ext | 400 | 67 | 77.7 | -10.7 | -13.8% | [-32% ; +5%] | 17.4 |


Regle choisie, par tranche de cote (Bet365 cloture -5%) :

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| (5, 6] | 274 | 47 | 49.7 | -2.7 | -5.4% | [-28% ; +19%] | 7.5 |
| (4, 5] | 230 | 38 | 50.2 | -12.2 | -24.3% | [-46% ; -2%] | 15.3 |
| (6, 8] | 36 | 1 | 4.8 | -3.8 | -79.4% | [-100% ; -37%] | 3.7 |


## Hypothese de cote : Bet365 cloture -10%

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 (marge 0%, plafond 6.0) | 194 | 27 | 38.5 | -11.5 | -29.9% | [-53% ; -6%] | 12.1 |
| 2024-25 (marge 20%, plafond 8.0) | 53 | 3 | 7.9 | -4.9 | -61.8% | [-100% ; -13%] | 5.5 |
| 2025-26 (marge 20%, plafond 8.0) | 54 | 4 | 8.3 | -4.3 | -51.8% | [-88% ; -3%] | 4.1 |
| 2026-27 (marge 0%, plafond 6.0) | 49 | 7 | 9.4 | -2.4 | -25.4% | [-68% ; +27%] | 3.3 |
| **TOTAL regle choisie sur le passe** | 350 | 41 | 64.1 | -23.1 | -36.0% | [-53% ; -18%] | 24.0 |
| Pari a l'aveugle (cote > 4) | 4746 | 550 | 779.1 | -229.1 | -29.4% | [-35% ; -24%] | 231.7 |
| Regle fixe : marge 0%, sans plafond | 1505 | 135 | 209.3 | -74.3 | -35.5% | [-46% ; -24%] | 74.9 |
| Regle fixe : marge 10%, sans plafond | 985 | 70 | 125.1 | -55.1 | -44.1% | [-56% ; -31%] | 55.2 |
| Regle fixe : marge 20%, sans plafond | 635 | 44 | 73.3 | -29.3 | -40.0% | [-56% ; -22%] | 29.8 |


## Hypothese de cote : Moyenne cloture

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 (marge 0%, plafond 8.0) | 706 | 104 | 125.3 | -21.3 | -17.0% | [-32% ; -1%] | 24.0 |
| 2024-25 (marge 0%, plafond 6.0) | 276 | 47 | 53.3 | -6.3 | -11.8% | [-34% ; +11%] | 8.7 |
| 2025-26 (marge 0%, plafond 6.0) | 238 | 44 | 46.9 | -2.9 | -6.2% | [-30% ; +20%] | 7.0 |
| 2026-27 (marge 10%, plafond 6.0) | 30 | 4 | 5.5 | -1.5 | -27.5% | [-82% ; +46%] | 2.8 |
| **TOTAL regle choisie sur le passe** | 1250 | 199 | 231.0 | -32.0 | -13.9% | [-24% ; -3%] | 35.1 |
| Pari a l'aveugle (cote > 4) | 7004 | 953 | 1166.5 | -213.5 | -18.3% | [-23% ; -14%] | 219.7 |
| Regle fixe : marge 0%, sans plafond | 2887 | 325 | 409.2 | -84.2 | -20.6% | [-29% ; -13%] | 88.6 |
| Regle fixe : marge 10%, sans plafond | 1949 | 188 | 252.2 | -64.2 | -25.4% | [-35% ; -15%] | 67.5 |
| Regle fixe : marge 20%, sans plafond | 1291 | 109 | 151.9 | -42.9 | -28.3% | [-41% ; -15%] | 45.7 |


## Hypothese de cote : Meilleure cote cloture

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 (marge 5%, plafond 6.0) | 462 | 72 | 90.9 | -18.9 | -20.8% | [-37% ; -4%] | 20.5 |
| 2024-25 (marge 15%, plafond 6.0) | 99 | 17 | 18.0 | -1.0 | -5.7% | [-45% ; +38%] | 4.4 |
| 2025-26 (marge 5%, plafond 8.0) | 481 | 82 | 81.2 | 0.8 | +1.0% | [-18% ; +21%] | 9.7 |
| 2026-27 (marge 5%, plafond 6.0) | 76 | 18 | 14.2 | 3.8 | +26.6% | [-22% ; +76%] | 3.3 |
| **TOTAL regle choisie sur le passe** | 1118 | 189 | 204.3 | -15.3 | -7.5% | [-20% ; +5%] | 27.8 |
| Pari a l'aveugle (cote > 4) | 8117 | 1190 | 1319.6 | -129.6 | -9.8% | [-15% ; -5%] | 139.4 |
| Regle fixe : marge 0%, sans plafond | 4181 | 507 | 580.1 | -73.1 | -12.6% | [-20% ; -5%] | 78.4 |
| Regle fixe : marge 10%, sans plafond | 3007 | 322 | 376.9 | -54.9 | -14.6% | [-23% ; -6%] | 59.5 |
| Regle fixe : marge 20%, sans plafond | 2163 | 199 | 246.4 | -47.4 | -19.2% | [-29% ; -9%] | 50.8 |
