---
icon: lucide/home
---

# Casita

Casita is a personal rental-search assistant for downtown Chicago, focused on
River North, South Loop, West Loop, and Fulton Market. It gathers listings,
enriches and ranks them against a renter's preferences, and publishes a static
page that is easier to review than several open browser tabs.

It did its job.

Casita is not a product or service. It is a personal-use tool, published as-is
under MIT, and this repo exists for an interview loop. The signal is what a
candidate chooses to improve.

## The Invitation

Fork the repo and make it your own. Pick something you think makes Casita
better: a fix, a test, a refactor, a feature, docs, polish, or a
simplification, and tell us why you chose it.

The code intentionally keeps the personal-tool shape. CTA access,
neighborhood walkability, in-unit laundry, A/C, and covered parking matter.
One-bedroom, den, and smaller two-bedroom layouts are preferred. Pets are not
a ranking factor. Those assumptions are configurable in the owning modules.

## Start Here

- Run the credentials-free demo: `uv run casita demo`
- Read [Getting Started](getting-started.md)
- Skim [How It Works](how-it-works/routing.md)
- Use [Architecture](architecture.md) when you want the module map
