# PRODUCT-HUNTER V4

Evergreen ecommerce product-research app built with Flask, Claude AI and an objective ranking engine.

## What V4 does

- Accepts up to 100 pasted ad blocks per run.
- Skips exact duplicates before spending Claude API credits.
- Uses Claude Sonnet 5 to understand each product, customer problem and buying motivation.
- Scores problem severity, frequency, emotional pressure, 35+ fit, evergreen strength, willingness to pay, value proposition, clarity, demo strength and market breadth.
- Penalizes commodity risk, seasonality and risky claims.
- Separately calculates ad longevity, evidence confidence and cross-seller market validation in Python.
- Combines Claude semantic analysis with objective evidence into a hybrid final score.
- Keeps a living Top 5 and replaces older candidates when stronger products are found.
- Prevents near-identical products from filling all five ranking positions.
- Country is displayed for research context but does not affect the score.

## Required environment variable

`ANTHROPIC_API_KEY`

Optional:

`ANTHROPIC_MODEL=claude-sonnet-5`

Never put the real API key in GitHub or frontend JavaScript. Set it as a secret environment variable on Render.

## Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 1 --threads 4
```

Health endpoint: `/health`

## Important

The score is a research decision-support system, not a guarantee of profit. Real validation still requires economics, supplier quality, creative testing, conversion data, refunds and customer feedback.
