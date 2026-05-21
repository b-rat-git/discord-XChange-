```

     $$$$$$\  $$\             $$\            $$$$$$\    $$\                          $$\
    $$  __$$\ $$ |            $$ |          $$  __$$\   $$ |                         $$ |
    $$ /  \__|$$ |$$\   $$\ $$$$$$\         $$ /  \__|$$$$$$\    $$$$$$\   $$$$$$$\  $$ |  $$\
    \$$$$$$\  $$ |$$ |  $$ |\_$$  _|        \$$$$$$\  \_$$  _|  $$  __$$\ $$  _____|$$ | $$  |
     \____$$\ $$ |$$ |  $$ |  $$ |           \____$$\   $$ |    $$ /  $$ |$$ /      $$$$$$  /
    $$\   $$ |$$ |$$ |  $$ |  $$ |$$\       $$\   $$ |  $$ |$$\ $$ |  $$ |$$ |      $$  _$$<
    \$$$$$$  |$$ |\$$$$$$  |  \$$$$  |      \$$$$$$  |  \$$$$  |\$$$$$$  |\$$$$$$$\ $$ | \$$\
     \______/ \__| \______/    \____/        \______/    \____/  \______/  \_______|\__|  \__|

               $$\   $$\ $$\   $$\                   $$\
               $$ |  $$ |$$ |  $$ |                   $$ |
          $$\  $$ |  $$ |\$$\ $$  | $$$$$$\  $$$$$$$\ $$$$$$$\   $$$$$$\  $$$$$$$\   $$$$$$\   $$$$$$\
          \$$\ \$$\  $$ | \$$$$  / $$  __$$\ $$  __$$\$$  __$$\  \____$$\ $$  __$$\ $$  __$$\ $$  __$$\
           \$$\ \$$\ $$ | $$  $$<  $$ /  $$ |$$ |  $$ |$$ |  $$ | $$$$$$$ |$$ |  $$ |$$ /  $$ |$$$$$$$$ |
            \$$\ \$$$$ / $$  /\$$\ $$ |  $$ |$$ |  $$ |$$ |  $$ |$$  __$$ |$$ |  $$ |$$ |  $$ |$$   ____|
             \$$\ \$$  / $$ /  $$ |\$$$$$$$\ $$ |  $$ |$$ |  $$ |\$$$$$$$ |$$ |  $$ |\$$$$$$$ |\$$$$$$$\
              \__| \__/  \__|  \__| \_______|\__|  \__|\__|  \__| \_______|\__|  \__| \____$$ | \_______|
                                                                                    $$\   $$ |
                                                                                    \$$$$$$  |
                                                                                     \______/

         ╔══════════════════════════════════════════════════════════════╗
         ║                                                              ║
         ║        $$$$     MARKET IS OPEN 24/7     $$$$                 ║
         ║                                                              ║
         ║    ▲                         ╱╲                              ║
         ║    │  ╱╲      ╱╲           ╱    ╲    ╱╲                      ║
         ║    │ ╱  ╲    ╱  ╲   ╱╲   ╱      ╲  ╱  ╲  ╱╲               ║
         ║    │╱    ╲  ╱    ╲ ╱  ╲ ╱        ╲╱    ╲╱  ╲ ╱╲           ║
         ║    │      ╲╱      ╲    ╲                     ╲╱  ╲──►      ║
         ║    └──────────────────────────────────────────────────►      ║
         ║                                                              ║
         ╚══════════════════════════════════════════════════════════════╝
```

# Slut Stock xXxchange

A Discord bot that runs a virtual stock exchange game where users' stock prices are driven by server engagement and activity.

## Features

### Economy
- **Daily Rewards** - Claim $500 daily with a 7-day streak bonus ($1,000)
- **Starting Cash** - Each user starts with $10,000
- **Hedge Funds** - Create a personal hedge fund with 15% monthly APY, deposit/withdraw funds, and send to an events wallet

### Trading
- **Buy / Sell** - Trade shares of other users' stocks
- **Short / Cover** - Short sell with collateral locking and 30-minute freeze windows
- **24/7 Market** - Trading is open around the clock with a weekly reset every Monday at 8:00 AM EST

### Stock Price Mechanics
- **Activity-Driven Pricing** - Stock prices adjust every 15 minutes based on user engagement (messages, voice chat, reactions, replies)
- **Trade Impact** - Buying and selling moves prices using a logarithmic impact formula
- **VC Ping Rewards** - First 10 users to join voice after a ping get a 20% price uptick, with a 50% stay bonus after 1 hour
- **Inactivity Decay** - Idle users see a 6% price decay every 4 hours
- **Moderation Penalty** - Timeouts and automod warnings trigger a 17% stock price drop
- **Price Floor** - Stock prices cannot drop below $70

### Leaderboards
- **Trending** - Top users ranked by stock price and 24-hour change
- **Losers** - Bottom users by trending score
- **My Stats** - Personal weekly engagement breakdown

### Other
- **Opt Out / Opt In** - Users can remove themselves from the stock exchange entirely
- **All-Time High Tracking** - Each user's ATH is recorded and displayed on their ticker
- **Auto-Delete** - Bot responses disappear after 15 seconds to keep channels clean

## Commands

| Command | Description |
|---------|-------------|
| `$balance` / `$mb` | View your cash, net worth, and hedge fund balance |
| `$daily` | Claim your daily reward |
| `$ticker [@user]` / `$price` | Check a user's stock price, 24h stats, and ATH |
| `$my_stock` | Quick view of your own stock |
| `$buy @user <shares>` | Buy shares of another user |
| `$sell @user <shares>` | Sell shares |
| `$short @user <shares>` | Short sell a user's stock |
| `$cover @user <shares>` | Cover a short position |
| `$portfolio [@user]` / `$pf` / `$mp` | View portfolio (long and short positions) |
| `$fund create [name]` | Create or rename your hedge fund |
| `$fund info [@user]` | View hedge fund details |
| `$fund deposit <amount>` | Deposit cash into your hedge fund |
| `$fund withdraw <amount>` | Withdraw from hedge fund to trading account |
| `$fund send_events <amount>` | Transfer to events wallet (no penalty) |
| `$mystats` | View your weekly engagement stats |
| `$trending` / `$leaderboard` / `$lb` | Top trending users |
| `$losers` | Bottom trending users |
| `$optout` | Opt out of the stock exchange |
| `$optin` | Opt back in |
| `$help` | Show all commands |

## Setup

### Requirements
- Python 3.8+
- discord.py
- python-dotenv

### Installation

```bash
pip install discord.py python-dotenv
```

### Configuration

Create a `.env` file in the project root:

```
DISCORD_TOKEN=your_bot_token_here
```

The bot requires the following Discord intents enabled in the [Developer Portal](https://discord.com/developers/applications):
- Message Content
- Server Members
- Reactions
- Voice States
- Moderation

### Running

```bash
python serverxchange.py
```

## Data Storage

All data is stored as JSON files in the `data/` directory:

| File | Contents |
|------|----------|
| `users.json` | User balances, portfolios, activity stats, daily streaks |
| `funds.json` | Hedge fund balances and investor data |
| `prices.json` | Stock prices, history, 24h highs/lows, ATH |
| `fund_penalties.json` | Early withdrawal penalty tracking |

```

## Authors

- **assalamagapeum**

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
