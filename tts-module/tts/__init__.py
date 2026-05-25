"""
Package "tts"
=============
Ce package regroupe la logique "cœur" du module Text-to-Speech :

- service.py        : appel à l'API Google Cloud Text-to-Speech (+ orchestration cache).
- cache.py          : cache sur disque des fichiers WAV déjà générés.
- announcements.py  : composition des annonces vocales + rate-limiting.

L'objectif de ce découpage est la LISIBILITÉ : chaque fichier a une seule
responsabilité claire, ce qui rend le code facile à expliquer et à défendre.
"""
