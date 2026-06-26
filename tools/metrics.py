"""Prometheus metrics for trading system monitoring."""

from prometheus_client import Counter, Histogram, Gauge

cycles_total = Counter("trading_cycles_total", "Total trading cycles", ["status"])
orders_total = Counter("orders_total", "Total orders placed", ["side", "status"])
llm_latency = Histogram("llm_request_seconds", "LLM request latency in seconds")
portfolio_value = Gauge("portfolio_value", "Current portfolio value in RUB")
drawdown_percent = Gauge("drawdown_percent", "Current drawdown percentage")
errors_total = Counter("errors_total", "Total errors by service", ["service"])
