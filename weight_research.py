"""Safe helpers for researching missing product weights."""
from urllib.parse import urlencode


def product_search_url(manufacturer, article):
    query = f'{str(manufacturer).strip()} {str(article).strip()} weight kg'
    return 'https://www.google.com/search?' + urlencode({'q': query})


def validate_weight(value):
    weight = float(str(value).replace(',', '.'))
    if not (0 < weight < 100000):
        raise ValueError('Waga musi być dodatnia i podana w kilogramach.')
    return weight

