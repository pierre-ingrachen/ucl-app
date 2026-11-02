# IA-optimisee : resultats (walk-forward, hors echantillon)

Candidats evalues : 13579 (victoire dom./ext. a cote moyenne >= 3.3, saisons 2021-22 a 2026-27).

Log-loss de P(victoire) sur ce segment : modele 0.4499 | taux de base constant 0.4589 | 1/cote moyenne du marche (non normalisee) 0.4435.


## Hypothese de cote : Bet365 cloture

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 (marge 5%, plafond 6.0) | 271 | 40 | 52.8 | -12.8 | -24.2% | [-45% ; -1%] | 17.1 |
| 2024-25 (marge 40%, plafond 12.0) | 74 | 2 | 8.5 | -6.5 | -76.4% | [-100% ; -40%] | 7.1 |
| 2025-26 (marge 5%, plafond 6.0) | 199 | 33 | 38.7 | -5.7 | -14.8% | [-43% ; +14%] | 9.0 |
| 2026-27 (marge 0%, plafond 6.0) | 72 | 15 | 13.8 | 1.2 | +9.0% | [-35% ; +58%] | 3.4 |
| **TOTAL regle choisie sur le passe** | 616 | 90 | 113.8 | -23.8 | -20.9% | [-35% ; -6%] | 30.7 |
| Pari a l'aveugle (cote > 4) | 5920 | 788 | 980.8 | -192.8 | -19.7% | [-25% ; -14%] | 196.5 |
| Regle fixe : marge 0%, sans plafond | 2474 | 283 | 356.4 | -73.4 | -20.6% | [-29% ; -12%] | 73.9 |
| Regle fixe : marge 10%, sans plafond | 1619 | 149 | 211.6 | -62.6 | -29.6% | [-40% ; -18%] | 62.6 |
| Regle fixe : marge 20%, sans plafond | 1092 | 84 | 131.0 | -47.0 | -35.9% | [-48% ; -22%] | 47.2 |


## Hypothese de cote : Bet365 cloture -5%

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 (marge 0%, plafond 6.0) | 248 | 37 | 49.8 | -12.8 | -25.8% | [-46% ; -3%] | 16.8 |
| 2024-25 (marge 30%, plafond 8.0) | 28 | 1 | 4.1 | -3.1 | -75.7% | [-100% ; -24%] | 3.0 |
| 2025-26 (marge 0%, plafond 6.0) | 212 | 35 | 41.7 | -6.7 | -16.1% | [-42% ; +9%] | 8.8 |
| 2026-27 (marge 5%, plafond 6.0) | 38 | 8 | 7.1 | 0.9 | +12.5% | [-57% ; +82%] | 1.7 |
| **TOTAL regle choisie sur le passe** | 526 | 81 | 102.8 | -21.8 | -21.2% | [-37% ; -5%] | 26.8 |
| Pari a l'aveugle (cote > 4) | 5390 | 690 | 898.4 | -208.4 | -23.2% | [-29% ; -18%] | 212.2 |
| Regle fixe : marge 0%, sans plafond | 1959 | 198 | 279.3 | -81.3 | -29.1% | [-38% ; -20%] | 81.2 |
| Regle fixe : marge 10%, sans plafond | 1257 | 106 | 162.3 | -56.3 | -34.7% | [-46% ; -22%] | 56.2 |
| Regle fixe : marge 20%, sans plafond | 814 | 55 | 95.5 | -40.5 | -42.4% | [-56% ; -28%] | 40.9 |


Regle choisie, par issue (Bet365 cloture -5%) :

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| dom | 133 | 14 | 25.8 | -11.8 | -45.7% | [-73% ; -15%] | 13.0 |
| ext | 393 | 67 | 77.0 | -10.0 | -13.0% | [-31% ; +7%] | 17.2 |


Regle choisie, par tranche de cote (Bet365 cloture -5%) :

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| (5, 6] | 254 | 42 | 45.8 | -3.8 | -8.3% | [-32% ; +18%] | 7.4 |
| (4, 5] | 249 | 38 | 53.8 | -15.8 | -29.4% | [-48% ; -9%] | 18.9 |
| (6, 8] | 23 | 1 | 3.2 | -2.2 | -68.8% | [-100% ; -5%] | 2.1 |


## Hypothese de cote : Bet365 cloture -10%

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 (marge 0%, plafond 6.0) | 210 | 30 | 42.0 | -12.0 | -28.5% | [-50% ; -4%] | 12.5 |
| 2024-25 (marge 20%, plafond 8.0) | 53 | 3 | 7.8 | -4.8 | -61.7% | [-100% ; -13%] | 5.5 |
| 2025-26 (marge 20%, plafond 8.0) | 59 | 5 | 9.2 | -4.2 | -45.7% | [-89% ; +6%] | 4.4 |
| 2026-27 (marge 0%, plafond 6.0) | 45 | 6 | 8.6 | -2.6 | -30.3% | [-77% ; +27%] | 2.6 |
| **TOTAL regle choisie sur le passe** | 367 | 44 | 67.6 | -23.6 | -34.9% | [-53% ; -16%] | 23.6 |
| Pari a l'aveugle (cote > 4) | 5050 | 623 | 861.1 | -238.1 | -27.7% | [-33% ; -22%] | 241.2 |
| Regle fixe : marge 0%, sans plafond | 1502 | 136 | 211.9 | -75.9 | -35.8% | [-45% ; -25%] | 75.8 |
| Regle fixe : marge 10%, sans plafond | 973 | 71 | 124.6 | -53.6 | -43.0% | [-55% ; -30%] | 53.7 |
| Regle fixe : marge 20%, sans plafond | 625 | 44 | 72.7 | -28.7 | -39.5% | [-55% ; -22%] | 29.2 |


## Hypothese de cote : Moyenne cloture

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 (marge 0%, plafond 6.0) | 438 | 76 | 88.3 | -12.3 | -13.9% | [-31% ; +5%] | 14.0 |
| 2024-25 (marge 0%, plafond 6.0) | 289 | 51 | 56.0 | -5.0 | -9.0% | [-30% ; +14%] | 8.7 |
| 2025-26 (marge 0%, plafond 6.0) | 248 | 47 | 49.1 | -2.1 | -4.3% | [-28% ; +21%] | 6.7 |
| 2026-27 (marge 0%, plafond 6.0) | 63 | 16 | 12.0 | 4.0 | +32.8% | [-24% ; +91%] | 1.7 |
| **TOTAL regle choisie sur le passe** | 1038 | 190 | 205.4 | -15.4 | -7.5% | [-20% ; +4%] | 22.1 |
| Pari a l'aveugle (cote > 4) | 7123 | 988 | 1200.6 | -212.6 | -17.7% | [-22% ; -13%] | 217.3 |
| Regle fixe : marge 0%, sans plafond | 2919 | 332 | 416.6 | -84.6 | -20.3% | [-28% ; -12%] | 86.6 |
| Regle fixe : marge 10%, sans plafond | 1963 | 186 | 256.0 | -70.0 | -27.3% | [-37% ; -18%] | 71.7 |
| Regle fixe : marge 20%, sans plafond | 1314 | 113 | 156.2 | -43.2 | -27.7% | [-40% ; -15%] | 46.0 |


## Hypothese de cote : Meilleure cote cloture

|  | paris | gagnes | mises | profit | ROI | IC95 | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 (marge 15%, plafond 6.0) | 292 | 48 | 57.1 | -9.1 | -15.9% | [-37% ; +7%] | 10.8 |
| 2024-25 (marge 15%, plafond 6.0) | 100 | 16 | 18.2 | -2.2 | -12.3% | [-50% ; +27%] | 5.1 |
| 2025-26 (marge 5%, plafond 8.0) | 493 | 83 | 83.4 | -0.4 | -0.5% | [-20% ; +19%] | 10.2 |
| 2026-27 (marge 5%, plafond 6.0) | 55 | 13 | 10.2 | 2.8 | +27.3% | [-31% ; +93%] | 2.3 |
| **TOTAL regle choisie sur le passe** | 940 | 160 | 168.9 | -8.9 | -5.3% | [-18% ; +9%] | 20.4 |
| Pari a l'aveugle (cote > 4) | 8073 | 1191 | 1320.5 | -129.5 | -9.8% | [-14% ; -5%] | 134.9 |
| Regle fixe : marge 0%, sans plafond | 4145 | 506 | 578.8 | -72.8 | -12.6% | [-20% ; -5%] | 76.1 |
| Regle fixe : marge 10%, sans plafond | 2977 | 324 | 375.4 | -51.4 | -13.7% | [-22% ; -5%] | 53.4 |
| Regle fixe : marge 20%, sans plafond | 2139 | 201 | 245.7 | -44.7 | -18.2% | [-29% ; -8%] | 46.3 |
