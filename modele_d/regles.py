"""Algorithme de paris a base de regles (pas d'IA) : outsider a cote > 4 en mauvaise forme."""


def parier(
    cote_outsider: float,
    outsider_est_domicile: bool,
    pct_victoires_dom: float,
    pct_victoires_ext: float,
    pct_invaincu_dom: float,
    pct_invaincu_ext: float,
    pct_victoires_lieu_dom: float,
    pct_victoires_lieu_ext: float,
) -> bool:
    """Renvoie True si on parie sur la victoire de l'outsider, False sinon.

    Parametres (pourcentages entre 0 et 100, sur les 5 derniers matchs) :
      cote_outsider            cote de la victoire de l'equipe outsider
      outsider_est_domicile    True si l'outsider joue a domicile
      pct_victoires_dom/ext    % de victoires de l'equipe a domicile / a l'exterieur
      pct_invaincu_dom/ext     % de matchs sans defaite (victoire ou nul)
      pct_victoires_lieu_dom   % de victoires de l'equipe a domicile, sur ses
                               5 derniers matchs a domicile
      pct_victoires_lieu_ext   % de victoires de l'equipe a l'exterieur, sur ses
                               5 derniers matchs a l'exterieur
    """
    # Regle retenue : l'outsider (cote > 4) n'a gagne qu'au plus 1 de ses 5 derniers matchs (<= 20 %).
    # Le marche surpaye la forme recente : plus l'outsider est en forme, plus le ROI est mauvais.
    pct_victoires_outsider = pct_victoires_dom if outsider_est_domicile else pct_victoires_ext
    return cote_outsider > 4 and pct_victoires_outsider <= 20
