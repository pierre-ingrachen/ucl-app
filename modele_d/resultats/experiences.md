# Experiences modele D

Scenario de selection : Bet365 cloture -5%. Dev = [2024, 2025], confirmation = [2026, 2027].

## Qualite des probabilites (log-loss : marche dev/conf = voir tableau D)

| modele | logloss dev | KL marche dev | logloss conf | KL marche conf |
|---|---|---|---|---|
| logit / ratings+xg / avgc / 1.0 | 0.9856 | 0.0143 | 0.9981 | 0.014 |
| logit / ratings+xg / avgc / 0.5 | 0.9856 | 0.0162 | 0.9992 | 0.0157 |
| hgb / ratings+xg / avgc / 1.0 | 0.9883 | 0.0145 | 0.9978 | 0.0136 |
| hgb / ratings+xg / avgc / 0.5 | 0.988 | 0.0151 | 0.9977 | 0.0141 |
| hgb / ratings+xg / avgc / 0.0 | 0.9896 | 0.0173 | 1.0005 | 0.0186 |
| hgb / ratings+xg / psc / 1.0 | 0.9878 | 0.0144 | 0.9976 | 0.0136 |
| hgb / ratings / avgc / 0.5 | 0.9881 | 0.0152 | 0.9978 | 0.0142 |
| hgb / base / avgc / 0.5 | 1.0106 | 0.0332 | 1.021 | 0.0326 |
| mlp / ratings+xg / avgc / 1.0 | 0.9869 | 0.0138 | 0.9985 | 0.0134 |
| mlp / ratings+xg / avgc / 0.5 | 0.9864 | 0.0158 | 0.9991 | 0.0152 |
| mlp / ratings / avgc / 0.5 | 0.9855 | 0.0153 | 0.9991 | 0.0154 |
| mlp / ratings+xg / psc / 0.5 | 0.9863 | 0.0159 | 0.999 | 0.0152 |

## 15 meilleures (modele, regle) selon le plus faible ROI de dev (Bet365 cloture -5%), puis leur resultat en confirmation

| modele | regle (ecart, plafond, issues, p min) | critere dev % | Bet365 cloture -10% dev (n, ROI%) | Bet365 cloture -10% CONF (n, ROI%, profit) | Bet365 cloture -5% dev (n, ROI%) | Bet365 cloture -5% CONF (n, ROI%, profit) | Bet365 cloture dev (n, ROI%) | Bet365 cloture CONF (n, ROI%, profit) |
|---|---|---|---|---|---|---|---|---|
| mlp / ratings+xg / psc / 0.5 | (0.2, 8.0, '2', 0.0) | 5.2 | 142, -15.0 | 119, -21.8, -4.7 | 199, 14.2 | 172, 6.3, 2.0 | 312, -3.8 | 272, 15.8, 7.9 |
| mlp / ratings+xg / psc / 0.5 | (0.2, 8.0, '2', 0.1) | 5.2 | 142, -15.0 | 119, -21.8, -4.7 | 199, 14.2 | 172, 6.3, 2.0 | 312, -3.8 | 272, 15.8, 7.9 |
| mlp / ratings+xg / psc / 0.5 | (0.2, 8.0, '2', 0.15) | 5.2 | 142, -15.0 | 119, -21.8, -4.7 | 199, 14.2 | 172, 6.3, 2.0 | 312, -3.8 | 272, 15.8, 7.9 |
| mlp / ratings / avgc / 0.5 | (0.2, 8.0, '2', 0.0) | 4.8 | 156, -7.8 | 110, -17.5, -3.6 | 212, 7.4 | 180, 1.8, 0.6 | 318, -6.5 | 274, 9.6, 4.9 |
| mlp / ratings / avgc / 0.5 | (0.2, 8.0, '2', 0.1) | 4.8 | 156, -7.8 | 110, -17.5, -3.6 | 212, 7.4 | 180, 1.8, 0.6 | 318, -6.5 | 274, 9.6, 4.9 |
| mlp / ratings / avgc / 0.5 | (0.2, 8.0, '2', 0.15) | 4.8 | 156, -7.8 | 110, -17.5, -3.6 | 212, 7.4 | 180, 1.8, 0.6 | 318, -6.5 | 274, 9.6, 4.9 |
| mlp / ratings+xg / avgc / 0.5 | (0.2, 8.0, '2', 0.0) | 2.8 | 157, -12.8 | 131, -12.6, -3.0 | 212, 9.5 | 187, 6.9, 2.4 | 329, -7.1 | 284, 15.0, 7.8 |
| mlp / ratings+xg / avgc / 0.5 | (0.2, 8.0, '2', 0.1) | 2.8 | 157, -12.8 | 131, -12.6, -3.0 | 212, 9.5 | 187, 6.9, 2.4 | 329, -7.1 | 284, 15.0, 7.8 |
| mlp / ratings+xg / avgc / 0.5 | (0.2, 8.0, '2', 0.15) | 2.8 | 157, -12.8 | 131, -12.6, -3.0 | 212, 9.5 | 187, 6.9, 2.4 | 329, -7.1 | 284, 15.0, 7.8 |
| hgb / ratings+xg / avgc / 0.5 | (0.2, 6.0, '2', 0.0) | -0.2 | 139, -4.3 | 85, -24.6, -4.2 | 192, 2.9 | 131, 4.9, 1.3 | 272, -5.2 | 206, -0.0, -0.0 |
| hgb / ratings+xg / avgc / 0.5 | (0.2, 6.0, '2', 0.1) | -0.2 | 139, -4.3 | 85, -24.6, -4.2 | 192, 2.9 | 131, 4.9, 1.3 | 272, -5.2 | 206, -0.0, -0.0 |
| hgb / ratings+xg / avgc / 0.5 | (0.2, 6.0, '2', 0.15) | -0.2 | 139, -4.3 | 85, -24.6, -4.2 | 192, 2.9 | 131, 4.9, 1.3 | 272, -5.2 | 206, -0.0, -0.0 |
| mlp / ratings+xg / avgc / 1.0 | (0.05, 5.0, 'N', 0.0) | -0.6 | 169, -12.4 | 129, -33.2, -9.4 | 293, 2.1 | 222, -8.7, -4.3 | 517, -11.6 | 424, -14.1, -13.3 |
| mlp / ratings+xg / avgc / 1.0 | (0.05, 5.0, 'N', 0.1) | -0.6 | 169, -12.4 | 129, -33.2, -9.4 | 293, 2.1 | 222, -8.7, -4.3 | 517, -11.6 | 424, -14.1, -13.3 |
| mlp / ratings+xg / avgc / 1.0 | (0.05, 5.0, 'N', 0.15) | -0.6 | 169, -12.4 | 129, -33.2, -9.4 | 293, 2.1 | 222, -8.7, -4.3 | 517, -11.6 | 424, -14.1, -13.3 |

## Effet de selection
Sur les 200 meilleures regles du dev (200 avec >= 30 paris en confirmation), ROI de confirmation (Bet365 cloture -5%) : mediane -8.2 %, moyenne -7.9 %, 21 % positives.
