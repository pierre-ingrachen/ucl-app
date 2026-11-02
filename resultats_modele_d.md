# Modele D : predire les cotes du marche a partir des features seules

28665 matchs avec cotes, 71 entrees (sans aucune cote), reseau 96-48, 5 graines. Tests : 15055 matchs des saisons 2023-24, 2024-25, 2025-26, 2026-27.

## Choix faits sur la saison de validation (jamais sur le test)
  base alpha=1.0  test 2023-24 : 8896 matchs d'entrainement, 34 epoques, seuils choisis sur validation : ecart 15%, plafond <= 6, ROI validation -24.3 %
  base alpha=1.0  test 2024-25 : 13610 matchs d'entrainement, 32 epoques, seuils choisis sur validation : ecart 40%, plafond <= 8, ROI validation -13.7 %
  base alpha=1.0  test 2025-26 : 18406 matchs d'entrainement, 28 epoques, seuils choisis sur validation : ecart 40%, plafond <= 6, ROI validation -6.1 %
  base alpha=1.0  test 2026-27 : 23173 matchs d'entrainement, 18 epoques, seuils choisis sur validation : ecart 25%, plafond <= 6, ROI validation -7.8 %
  base alpha=0.5  test 2023-24 : 8896 matchs d'entrainement, 16 epoques, seuils choisis sur validation : ecart 30%, plafond <= 8, ROI validation -12.2 %
  base alpha=0.5  test 2024-25 : 13610 matchs d'entrainement, 16 epoques, seuils choisis sur validation : ecart 40%, plafond <= 8, ROI validation -20.8 %
  base alpha=0.5  test 2025-26 : 18406 matchs d'entrainement, 12 epoques, seuils choisis sur validation : ecart 40%, plafond <= 6, ROI validation -7.1 %
  base alpha=0.5  test 2026-27 : 23173 matchs d'entrainement, 17 epoques, seuils choisis sur validation : ecart 15%, plafond <= 6, ROI validation -15.4 %
  base alpha=0.0  test 2023-24 : 8896 matchs d'entrainement, 9 epoques, seuils choisis sur validation : ecart 30%, plafond <= 6, ROI validation -14.8 %
  base alpha=0.0  test 2024-25 : 13610 matchs d'entrainement, 11 epoques, seuils choisis sur validation : ecart 40%, plafond <= 8, ROI validation -11.6 %
  base alpha=0.0  test 2025-26 : 18406 matchs d'entrainement, 8 epoques, seuils choisis sur validation : ecart 30%, plafond <= 6, ROI validation -1.8 %
  base alpha=0.0  test 2026-27 : 23173 matchs d'entrainement, 7 epoques, seuils choisis sur validation : ecart 30%, plafond <= 6, ROI validation -12.8 %
  +ratings alpha=1.0  test 2023-24 : 8896 matchs d'entrainement, 35 epoques, seuils choisis sur validation : ecart 30%, plafond <= 8, ROI validation -11.3 %
  +ratings alpha=1.0  test 2024-25 : 13610 matchs d'entrainement, 46 epoques, seuils choisis sur validation : ecart 30%, plafond <= 8, ROI validation -2.1 %
  +ratings alpha=1.0  test 2025-26 : 18406 matchs d'entrainement, 51 epoques, seuils choisis sur validation : ecart 25%, plafond <= 6, ROI validation -7.4 %
  +ratings alpha=1.0  test 2026-27 : 23173 matchs d'entrainement, 29 epoques, seuils choisis sur validation : ecart 25%, plafond <= 6, ROI validation -11.1 %
  +ratings alpha=0.5  test 2023-24 : 8896 matchs d'entrainement, 9 epoques, seuils choisis sur validation : ecart 30%, plafond <= 8, ROI validation -0.6 %
  +ratings alpha=0.5  test 2024-25 : 13610 matchs d'entrainement, 9 epoques, seuils choisis sur validation : ecart 40%, plafond sans plafond, ROI validation 29.5 %
  +ratings alpha=0.5  test 2025-26 : 18406 matchs d'entrainement, 12 epoques, seuils choisis sur validation : ecart 10%, plafond <= 6, ROI validation -13.3 %
  +ratings alpha=0.5  test 2026-27 : 23173 matchs d'entrainement, 10 epoques, seuils choisis sur validation : ecart 25%, plafond <= 6, ROI validation -7.4 %
  +ratings alpha=0.0  test 2023-24 : 8896 matchs d'entrainement, 7 epoques, seuils choisis sur validation : ecart 15%, plafond <= 6, ROI validation -12.2 %
  +ratings alpha=0.0  test 2024-25 : 13610 matchs d'entrainement, 8 epoques, seuils choisis sur validation : ecart 40%, plafond <= 8, ROI validation -5.3 %
  +ratings alpha=0.0  test 2025-26 : 18406 matchs d'entrainement, 8 epoques, seuils choisis sur validation : ecart 10%, plafond <= 6, ROI validation -14.7 %
  +ratings alpha=0.0  test 2026-27 : 23173 matchs d'entrainement, 8 epoques, seuils choisis sur validation : ecart 20%, plafond <= 6, ROI validation -9.9 %

## Qualite des probabilites sur les saisons de test
| modele (alpha) | log-loss vs resultats | ecart moyen au marche (|p - p_marche|) | KL vs marche |
|---|---|---|---|
| D base alpha=1.0 | 1.0102 | 0.0591 | 0.0290 |
| D base alpha=0.5 | 1.0106 | 0.0604 | 0.0302 |
| D base alpha=0.0 | 1.0126 | 0.0635 | 0.0330 |
| D +ratings alpha=1.0 | 0.9910 | 0.0404 | 0.0135 |
| D +ratings alpha=0.5 | 0.9902 | 0.0426 | 0.0150 |
| D +ratings alpha=0.0 | 0.9911 | 0.0466 | 0.0181 |
| marche lui-meme | 0.9691 | 0 | 0 |

## Resultats de paris hors echantillon (mise = 1/cote, cote proposee > 4)
alpha = poids du marche dans la cible. ROI = profit / total mise. IC95 par rééchantillonnage des paris. CLV = mean(cote prise x proba juste de cloture - 1).

### Cote proposee : Bet365 cloture -10%
| modele | paris | gagnes | profit | mises | roi_% | ic95_% | drawdown | CLV_% |
|---|---|---|---|---|---|---|---|---|
| pari a l'aveugle (toute cote > 4) | 7723 | 1055 | -336.38 | 1391.38 | -24.2 | [-28.5 ; -20.1] | 338.76 |  |
| D base alpha=1.0 | 717 | 98 | -43.62 | 141.62 | -30.8 | [-42.8 ; -18.1] | 45.03 | -14.3 |
| D base alpha=0.5 | 564 | 83 | -21.06 | 104.06 | -20.2 | [-35.8 ; -4.6] | 24.16 | -14.2 |
| D base alpha=0.0 | 518 | 82 | -18.7 | 100.7 | -18.6 | [-34.0 ; -1.7] | 20.58 | -14.0 |
| D +ratings alpha=1.0 | 271 | 39 | -10.77 | 49.77 | -21.6 | [-44.2 ; 1.7] | 11.91 | -13.1 |
| D +ratings alpha=0.5 | 521 | 81 | -21.34 | 102.34 | -20.9 | [-36.5 ; -5.1] | 23.73 | -13.3 |
| D +ratings alpha=0.0 | 550 | 83 | -30.15 | 113.15 | -26.6 | [-40.8 ; -11.8] | 32.6 | -13.3 |

### Cote proposee : Bet365 cloture -5%
| modele | paris | gagnes | profit | mises | roi_% | ic95_% | drawdown | CLV_% |
|---|---|---|---|---|---|---|---|---|
| pari a l'aveugle (toute cote > 4) | 8481 | 1202 | -300.42 | 1502.42 | -20.0 | [-24.2 ; -16.0] | 303.71 |  |
| D base alpha=1.0 | 812 | 126 | -34.11 | 160.11 | -21.3 | [-33.8 ; -8.3] | 37.91 | -9.5 |
| D base alpha=0.5 | 696 | 119 | -9.23 | 128.23 | -7.2 | [-21.4 ; 7.9] | 14.95 | -9.4 |
| D base alpha=0.0 | 621 | 106 | -14.28 | 120.28 | -11.9 | [-26.7 ; 2.8] | 19.68 | -9.3 |
| D +ratings alpha=1.0 | 372 | 55 | -13.08 | 68.08 | -19.2 | [-38.8 ; 0.9] | 15.5 | -8.2 |
| D +ratings alpha=0.5 | 719 | 113 | -26.5 | 139.5 | -19.0 | [-32.0 ; -4.8] | 30.49 | -8.5 |
| D +ratings alpha=0.0 | 759 | 125 | -31.97 | 156.97 | -20.4 | [-32.8 ; -7.6] | 36.02 | -8.5 |

### Cote proposee : Bet365 cloture
| modele | paris | gagnes | profit | mises | roi_% | ic95_% | drawdown | CLV_% |
|---|---|---|---|---|---|---|---|---|
| pari a l'aveugle (toute cote > 4) | 9667 | 1442 | -270.3 | 1712.3 | -15.8 | [-19.8 ; -11.9] | 272.81 |  |
| D base alpha=1.0 | 1142 | 180 | -40.13 | 220.13 | -18.2 | [-29.0 ; -7.1] | 42.37 | -4.8 |
| D base alpha=0.5 | 960 | 151 | -22.79 | 173.79 | -13.1 | [-26.4 ; 0.6] | 26.58 | -4.7 |
| D base alpha=0.0 | 867 | 151 | -14.45 | 165.45 | -8.7 | [-21.8 ; 4.1] | 18.93 | -4.5 |
| D +ratings alpha=1.0 | 585 | 87 | -19.53 | 106.53 | -18.3 | [-33.6 ; -1.3] | 19.92 | -3.6 |
| D +ratings alpha=0.5 | 1085 | 190 | -21.96 | 211.96 | -10.4 | [-21.7 ; 1.0] | 24.55 | -3.8 |
| D +ratings alpha=0.0 | 1164 | 209 | -31.2 | 240.2 | -13.0 | [-23.7 ; -2.1] | 32.17 | -3.9 |

### Cote proposee : Moyenne marche -10%
| modele | paris | gagnes | profit | mises | roi_% | ic95_% | drawdown | CLV_% |
|---|---|---|---|---|---|---|---|---|
| pari a l'aveugle (toute cote > 4) | 8784 | 1190 | -388.93 | 1578.93 | -24.6 | [-28.6 ; -20.8] | 391.15 |  |
| D base alpha=1.0 | 891 | 114 | -62.08 | 176.08 | -35.3 | [-46.6 ; -23.6] | 64.05 | -14.9 |
| D base alpha=0.5 | 680 | 100 | -22.89 | 122.89 | -18.6 | [-33.0 ; -3.7] | 26.03 | -15.1 |
| D base alpha=0.0 | 565 | 90 | -18.68 | 108.68 | -17.2 | [-33.4 ; -1.6] | 26.87 | -15.1 |
| D +ratings alpha=1.0 | 301 | 42 | -12.25 | 54.25 | -22.6 | [-43.5 ; -0.4] | 13.13 | -15.0 |
| D +ratings alpha=0.5 | 485 | 68 | -24.54 | 92.54 | -26.5 | [-42.7 ; -10.0] | 25.36 | -15.7 |
| D +ratings alpha=0.0 | 533 | 81 | -28.88 | 109.88 | -26.3 | [-40.3 ; -11.8] | 30.8 | -15.4 |

## Detail par saison (Bet365 cloture -10%)
D base alpha=1.0
| saison | seuils | paris | gagnes | profit | mises | roi_% | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 | ecart 15%, <= 6 | 442 | 60 | -30.03 | 90.03 | -33.4 | 31.38 |
| 2024-25 | ecart 40%, <= 8 | 130 | 16 | -6.38 | 22.38 | -28.5 | 7.32 |
| 2025-26 | ecart 40%, <= 6 | 65 | 10 | -3.06 | 13.06 | -23.4 | 4.53 |
| 2026-27 | ecart 25%, <= 6 | 80 | 12 | -4.16 | 16.16 | -25.7 | 5.56 |

D base alpha=0.5
| saison | seuils | paris | gagnes | profit | mises | roi_% | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 | ecart 30%, <= 8 | 247 | 31 | -12.13 | 43.13 | -28.1 | 12.66 |
| 2024-25 | ecart 40%, <= 8 | 118 | 17 | -3.28 | 20.28 | -16.2 | 5.07 |
| 2025-26 | ecart 40%, <= 6 | 63 | 11 | -1.71 | 12.71 | -13.5 | 4.14 |
| 2026-27 | ecart 15%, <= 6 | 136 | 24 | -3.93 | 27.93 | -14.1 | 6.75 |

D base alpha=0.0
| saison | seuils | paris | gagnes | profit | mises | roi_% | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 | ecart 30%, <= 6 | 167 | 24 | -9.49 | 33.49 | -28.3 | 9.49 |
| 2024-25 | ecart 40%, <= 8 | 127 | 16 | -5.79 | 21.79 | -26.6 | 7.7 |
| 2025-26 | ecart 30%, <= 6 | 165 | 34 | 0.31 | 33.69 | 0.9 | 6.12 |
| 2026-27 | ecart 30%, <= 6 | 59 | 8 | -3.72 | 11.72 | -31.8 | 4.68 |

D +ratings alpha=1.0
| saison | seuils | paris | gagnes | profit | mises | roi_% | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 | ecart 30%, <= 8 | 72 | 12 | -0.62 | 12.62 | -4.9 | 2.63 |
| 2024-25 | ecart 30%, <= 8 | 92 | 10 | -5.75 | 15.75 | -36.5 | 7.66 |
| 2025-26 | ecart 25%, <= 6 | 76 | 14 | -1.38 | 15.38 | -9.0 | 4.16 |
| 2026-27 | ecart 25%, <= 6 | 31 | 3 | -3.03 | 6.03 | -50.2 | 3.84 |

D +ratings alpha=0.5
| saison | seuils | paris | gagnes | profit | mises | roi_% | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 | ecart 30%, <= 8 | 63 | 8 | -3.13 | 11.13 | -28.1 | 4.32 |
| 2024-25 | ecart 40%, sans plafond | 46 | 3 | -2.87 | 5.87 | -48.9 | 2.92 |
| 2025-26 | ecart 10%, <= 6 | 380 | 64 | -14.94 | 78.94 | -18.9 | 15.69 |
| 2026-27 | ecart 25%, <= 6 | 32 | 6 | -0.41 | 6.41 | -6.3 | 1.6 |

D +ratings alpha=0.0
| saison | seuils | paris | gagnes | profit | mises | roi_% | drawdown |
|---|---|---|---|---|---|---|---|
| 2023-24 | ecart 15%, <= 6 | 165 | 20 | -13.82 | 33.82 | -40.9 | 13.82 |
| 2024-25 | ecart 40%, <= 8 | 20 | 1 | -2.4 | 3.4 | -70.6 | 2.4 |
| 2025-26 | ecart 10%, <= 6 | 318 | 52 | -14.42 | 66.42 | -21.7 | 14.5 |
| 2026-27 | ecart 20%, <= 6 | 47 | 10 | 0.5 | 9.5 | 5.2 | 1.95 |

## Sensibilite aux seuils, D base alpha=0.0 (meilleur ROI du scenario principal), memes seuils appliques a toutes les saisons de test. Descriptif uniquement.
| plafond de cote | ecart exige | paris | roi_% | profit |
|---|---|---|---|---|
| <= 6 | 5% | 2458 | -22.6 | -116.32 |
| <= 6 | 10% | 1996 | -24.4 | -100.99 |
| <= 6 | 15% | 1555 | -21.2 | -67.72 |
| <= 6 | 20% | 1152 | -22.1 | -51.78 |
| <= 6 | 25% | 827 | -19.5 | -32.79 |
| <= 6 | 30% | 549 | -15.4 | -17.13 |
| <= 6 | 40% | 213 | -19.0 | -8.19 |
| <= 8 | 5% | 3351 | -23.4 | -151.13 |
| <= 8 | 10% | 2803 | -24.8 | -131.98 |
| <= 8 | 15% | 2272 | -22.3 | -94.54 |
| <= 8 | 20% | 1751 | -23.0 | -73.98 |
| <= 8 | 25% | 1327 | -21.4 | -51.32 |
| <= 8 | 30% | 961 | -18.6 | -31.82 |
| <= 8 | 40% | 421 | -24.9 | -18.24 |
| <= 12 | 5% | 4135 | -26.4 | -192.19 |
| <= 12 | 10% | 3525 | -28.0 | -170.36 |
| <= 12 | 15% | 2936 | -25.9 | -127.79 |
| <= 12 | 20% | 2368 | -27.7 | -107.14 |
| <= 12 | 25% | 1864 | -26.9 | -79.85 |
| <= 12 | 30% | 1413 | -25.8 | -56.22 |
| <= 12 | 40% | 710 | -31.2 | -32.26 |
| sans plafond | 5% | 4427 | -27.4 | -204.5 |
| sans plafond | 10% | 3803 | -29.0 | -181.77 |
| sans plafond | 15% | 3194 | -27.0 | -137.92 |
| sans plafond | 20% | 2609 | -29.1 | -117.14 |
| sans plafond | 25% | 2086 | -28.8 | -89.57 |
| sans plafond | 30% | 1616 | -28.1 | -64.72 |
| sans plafond | 40% | 862 | -34.3 | -38.6 |
