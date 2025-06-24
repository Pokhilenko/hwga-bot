Feci quod potui faciant meliora potentes

Bot link: [https://t.me/hwga_sausage_bot](https://t.me/hwga_sausage_bot)

## Wallet Integration

This repository includes a basic skeleton for synchronising transactions with
BudgetBakers Wallet. The `WalletClient` class in `wallet.py` now exposes
asynchronous methods for creating, reading, updating and deleting transactions
via the wallet service. The real API calls still rely on the unofficial
`WalletAPI` package or the BudgetBakers Open Banking API.
