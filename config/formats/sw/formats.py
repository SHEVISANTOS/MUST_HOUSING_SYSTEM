# Tanzanian convention: TZS 150,000 - Django's built-in Swahili format has
# no thousands grouping, which made rents read as "TZS 4668660".
DECIMAL_SEPARATOR = '.'
THOUSAND_SEPARATOR = ','
NUMBER_GROUPING = 3
DATE_FORMAT = 'j F Y'
SHORT_DATE_FORMAT = 'd/m/Y'
