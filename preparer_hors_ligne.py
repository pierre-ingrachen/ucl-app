"""OBSOLETE. Ce script prechargeait les donnees TheSportsDB pour le mode hors ligne (`ucl-1510`).

Depuis la branche free-ucl, toutes les donnees du site (matchs, classements, clubs, pays, logos) sont dans la
base locale `calendrier/base/`, versionnee et mise a jour par le workflow : le mode hors ligne n'a plus rien a
precharger. Lancer simplement `ucl-1510` (UCL_HORS_LIGNE=1) : le backend sert la base locale sans aucun appel reseau.
"""
import sys

sys.exit(__doc__)
