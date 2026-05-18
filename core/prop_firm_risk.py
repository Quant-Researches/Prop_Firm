import logging

logger = logging.getLogger("PropFirmRisk")

class PropFirmRiskManager:
    """
    Evaluates account risk against proprietary firm rules,
    such as daily drawdown limits and max drawdown limits.
    """
    def __init__(self, daily_drawdown_limit=5.0, max_drawdown_limit=10.0):
        self.daily_drawdown_limit = daily_drawdown_limit
        self.max_drawdown_limit = max_drawdown_limit

    def evaluate_risk(self, account_balance, current_equity, start_of_day_equity):
        warnings = []
        if account_balance <= 0 or start_of_day_equity <= 0:
            return warnings
            
        daily_dd_pct = ((start_of_day_equity - current_equity) / start_of_day_equity) * 100
        if daily_dd_pct >= self.daily_drawdown_limit:
            warnings.append(f"DAILY DRAWDOWN LIMIT EXCEEDED: {daily_dd_pct:.2f}% >= {self.daily_drawdown_limit}%")
            
        max_dd_pct = ((account_balance - current_equity) / account_balance) * 100
        if max_dd_pct >= self.max_drawdown_limit:
            warnings.append(f"MAX DRAWDOWN LIMIT EXCEEDED: {max_dd_pct:.2f}% >= {self.max_drawdown_limit}%")
            
        return warnings
