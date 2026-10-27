# VOT House Finding / MUST Housing: design handoff pack

- css/tokens.css      design tokens (load first)
- css/components.css  14 components as `vh-` classes
- icons/*.svg         24 icons (24px grid, 1.8 stroke, currentColor); icons/sprite.svg = all of them as <symbol id="i-NAME">
- templates/_listing_card.html  Django include for search results, uses today's model fields
- tokens.json         same tokens for Figma (Tokens Studio plugin)
- demo.html           every component on one page; open it next to the design canvas

Adopt page by page: link both CSS files in base.html after Bootstrap, paste sprite.svg once after <body>,
rebuild one template with vh- classes, check at 360px, repeat. See the spec doc, section 9.
