/**
 * Trading Agents Live Stream — WebSocket Client + Charts
 */

class TradingDashboard {
    constructor() {
        this.ws = null;
        this.reconnectInterval = 3000;
        this.maxSpeedForBar = 60; // Max tok/s for progress bar scaling
        this.maxVramForBar = 16; // Max GB for VRAM bar scaling

        this.initWebSocket();
        this.initCharts();
    }

    // ── WebSocket ──

    initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/live`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.updateConnectionStatus(true);
            // Start ping
            this.pingInterval = setInterval(() => {
                if (this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send('ping');
                }
            }, 30000);
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data !== 'pong') {
                    this.updateDashboard(data);
                }
            } catch (e) {
                console.error('Parse error:', e);
            }
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.updateConnectionStatus(false);
            clearInterval(this.pingInterval);
            // Reconnect
            setTimeout(() => this.initWebSocket(), this.reconnectInterval);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    updateConnectionStatus(connected) {
        const dot = document.getElementById('ws-status');
        const text = document.getElementById('connection-status');
        if (connected) {
            dot.className = 'status-dot connected';
            text.textContent = 'Connected';
        } else {
            dot.className = 'status-dot disconnected';
            text.textContent = 'Disconnected';
        }
    }

    // ── Charts ──

    initCharts() {
        // Speed History Chart
        this.speedChart = Plotly.newPlot('speed-chart', [{
            y: [],
            type: 'bar',
            marker: {
                color: '#00ff88',
                opacity: 0.7,
            },
        }], {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            margin: { l: 40, r: 10, t: 10, b: 30 },
            xaxis: {
                showgrid: false,
                showticklabels: false,
            },
            yaxis: {
                showgrid: true,
                gridcolor: '#1e1e30',
                color: '#666',
                range: [0, this.maxSpeedForBar],
            },
        }, { displayModeBar: false, responsive: false });

        // Equity Curve Chart
        this.equityChart = Plotly.newPlot('equity-chart', [{
            x: [],
            y: [],
            type: 'scatter',
            mode: 'lines',
            fill: 'tozeroy',
            line: { color: '#6366f1', width: 2 },
            fillcolor: 'rgba(99, 102, 241, 0.1)',
        }], {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            margin: { l: 60, r: 10, t: 10, b: 40 },
            xaxis: {
                showgrid: true,
                gridcolor: '#1e1e30',
                color: '#666',
            },
            yaxis: {
                showgrid: true,
                gridcolor: '#1e1e30',
                color: '#666',
                tickprefix: '₽',
            },
        }, { displayModeBar: false, responsive: false });
    }

    // ── Update Dashboard ──

    updateDashboard(data) {
        this.updatePortfolio(data.portfolio);
        this.updateLMStudio(data.lmstudio);
        this.updateAgents(data.agents);
        this.updateTrades(data.last_trades);
        this.updateEquityCurve(data.equity_curve);
    }

    updatePortfolio(portfolio) {
        if (!portfolio) return;

        document.getElementById('balance').textContent =
            this.formatNumber(portfolio.balance) + ' ₽';

        const pnlEl = document.getElementById('pnl');
        pnlEl.textContent = (portfolio.pnl_percent >= 0 ? '+' : '') +
            portfolio.pnl_percent.toFixed(1) + '%';
        pnlEl.className = 'metric-value ' +
            (portfolio.pnl_percent >= 0 ? 'positive' : 'negative');

        document.getElementById('positions-count').textContent =
            portfolio.positions_count + '/10';
        document.getElementById('leverage').textContent =
            portfolio.leverage.toFixed(1) + 'x';
    }

    updateLMStudio(lmstudio) {
        if (!lmstudio) return;

        // Model and status
        document.getElementById('lm-model').textContent =
            'Model: ' + (lmstudio.model || '--');
        const statusEl = document.getElementById('lm-status');
        statusEl.textContent = 'Status: ' + (lmstudio.status || '--');
        statusEl.style.color = lmstudio.status === 'online' ? '#00ff88' : '#ff4444';

        // Speed progress bar
        const speedPercent = Math.min(
            (lmstudio.tokens_per_sec / this.maxSpeedForBar) * 100, 100
        );
        document.getElementById('speed-bar').style.width = speedPercent + '%';
        document.getElementById('speed-value').textContent =
            lmstudio.tokens_per_sec.toFixed(1) + ' tok/s';

        // VRAM progress bar
        if (lmstudio.gpu && lmstudio.gpu.available) {
            const vramPercent = Math.min(
                (lmstudio.gpu.vram_used / this.maxVramForBar) * 100, 100
            );
            document.getElementById('vram-bar').style.width = vramPercent + '%';
            document.getElementById('vram-value').textContent =
                lmstudio.gpu.vram_used.toFixed(1) + ' / ' +
                lmstudio.gpu.vram_total.toFixed(1) + ' GB';
        } else {
            document.getElementById('vram-bar').style.width = '0%';
            document.getElementById('vram-value').textContent = 'N/A';
        }

        // Stats
        document.getElementById('last-gen').textContent =
            lmstudio.last_completion_tokens + ' tok / ' +
            lmstudio.last_response_time.toFixed(2) + 's';
        document.getElementById('avg-speed').textContent =
            lmstudio.avg_tokens_per_sec.toFixed(1) + ' tok/s';
        document.getElementById('total-tokens').textContent =
            this.formatNumber(lmstudio.total_completion_tokens) + ' tokens';
        document.getElementById('total-requests').textContent =
            lmstudio.total_requests.toString();

        // Speed History Chart
        if (lmstudio.speed_history && lmstudio.speed_history.length > 0) {
            Plotly.update('speed-chart', {
                y: [lmstudio.speed_history],
            }, {
                'yaxis.range': [0, Math.max(
                    this.maxSpeedForBar,
                    Math.max(...lmstudio.speed_history) * 1.2
                )],
            });
        }
    }

    updateAgents(agents) {
        if (!agents) return;

        const container = document.getElementById('agents-list');
        const agentNames = [
            'NewsIntelligence', 'MarketData',
            'Strategy_trend', 'Strategy_contrarian', 'Strategy_bearish',
            'Critic', 'RiskManager', 'PortfolioManager', 'Execution', 'Memory'
        ];

        let html = '';
        for (const name of agentNames) {
            const agent = agents[name] || { status: 'idle', detail: '' };
            const statusClass = agent.status === 'active' ? 'active' : 'idle';
            const displayName = name.replace('Strategy_', 'Strategy: ');

            html += `
                <div class="agent-row ${statusClass}">
                    <div class="agent-indicator"></div>
                    <span class="agent-name">${displayName}</span>
                    <span class="agent-detail">${agent.detail || ''}</span>
                </div>
            `;
        }
        container.innerHTML = html;
    }

    updateTrades(trades) {
        if (!trades || trades.length === 0) return;

        const container = document.getElementById('trades-list');
        let html = '';

        for (const trade of trades.slice(0, 8)) {
            const isWin = trade.pnl >= 0;
            const resultClass = isWin ? 'win' : 'loss';
            const pnlClass = isWin ? 'positive' : 'negative';
            const sideClass = trade.side === 'LONG' ? 'long' : 'short';

            html += `
                <div class="trade-row">
                    <div class="trade-result ${resultClass}">${isWin ? '+' : '-'}</div>
                    <span class="trade-ticker">${trade.ticker}</span>
                    <span class="trade-side ${sideClass}">${trade.side}</span>
                    <span class="trade-pnl ${pnlClass}">
                        ${trade.pnl >= 0 ? '+' : ''}${trade.pnl_percent}%
                    </span>
                    <span class="trade-time">${trade.time || ''}</span>
                </div>
            `;
        }
        container.innerHTML = html;
    }

    updateEquityCurve(curve) {
        if (!curve || curve.length === 0) return;

        const x = curve.map(p => p[0]);
        const y = curve.map(p => p[1]);

        Plotly.update('equity-chart', {
            x: [x],
            y: [y],
        }, {});
    }

    // ── Utilities ──

    formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(2) + 'M';
        }
        if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toFixed(0);
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new TradingDashboard();
});
