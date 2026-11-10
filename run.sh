# Arrête le script à la première erreur
set -e

python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py runserver