// NFL Fantasy Predictor - Modern JavaScript Application

class NFLFantasyApp {
    constructor() {
        // Initialize with default values - will be updated by loadCurrentWeek()
        this.currentWeek = null;
        this.currentSeason = null;
        this.currentScoring = 'FanDuel';
        this.activeTab = 'QB';
        this.init();
    }

    async init() {
        console.log('🏈 Initializing NFL Fantasy Predictor...');
        
        // Bind event listeners
        this.bindEvents();
        
        // Load initial data
        await this.loadInitialData();
        
        // Setup historical toggle functionality (after DOM is ready)
        this.setupHistoricalToggle();
        
        console.log('✅ App initialized successfully');
    }

    bindEvents() {
        // Control panel buttons
        document.getElementById('get-predictions')?.addEventListener('click', () => this.getPredictions());
        document.getElementById('refresh-injuries')?.addEventListener('click', () => this.showInjuryReport());
        document.getElementById('update-data')?.addEventListener('click', () => this.updateData());
        document.getElementById('initialize-database')?.addEventListener('click', () => this.initializeDatabase());
        
        // Form inputs
        document.getElementById('scoring-system')?.addEventListener('change', (e) => {
            this.currentScoring = e.target.value;
        });
        
        document.getElementById('week-select')?.addEventListener('change', (e) => {
            this.currentWeek = parseInt(e.target.value);
            this.loadSchedule();
        });
        
        document.getElementById('season-select')?.addEventListener('change', (e) => {
            this.currentSeason = parseInt(e.target.value);
            this.loadSchedule();
        });
        
        // Position tabs
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.position);
            });
        });
        
        // Modal close
        document.addEventListener('click', (e) => {
            if (e.target.matches('.modal')) {
                this.closeModal(e.target.id);
            }
        });
    }

    async loadInitialData() {
        // Check initialization status first
        await this.checkInitializationStatus();
        
        // Load scoring systems
        await this.loadScoringSystems();
        
        // Load current week info
        await this.loadCurrentWeek();
        
        // Load initial schedule
        await this.loadSchedule();
        
        // Update last updated time
        this.updateLastUpdated();
    }

    async loadScoringSystems() {
        try {
            const response = await fetch('/api/scoring-systems');
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const systems = await response.json();
            
            const select = document.getElementById('scoring-system');
            if (select && systems && systems.length > 0) {
                // If the current default isn't available, fall back to the first system
                if (!systems.includes(this.currentScoring)) {
                    this.currentScoring = systems[0];
                }
                select.innerHTML = systems.map(system => 
                    `<option value="${system}" ${system === this.currentScoring ? 'selected' : ''}>${system}</option>`
                ).join('');
                console.log('✅ Loaded scoring systems:', systems);
            } else {
                console.warn('⚠️ No scoring systems received or select element not found');
                if (select) {
                    select.innerHTML = '<option value="">No systems available</option>';
                }
            }
        } catch (error) {
            console.error('❌ Failed to load scoring systems:', error);
            const select = document.getElementById('scoring-system');
            if (select) {
                select.innerHTML = '<option value="">Failed to load</option>';
            }
            this.showError('Failed to load scoring systems: ' + error.message);
        }
    }

    async loadCurrentWeek() {
        try {
            const response = await fetch('/api/current-week');
            const data = await response.json();
            
            this.currentWeek = data.week;
            this.currentSeason = data.season;
            
            // Update UI
            document.getElementById('current-week').textContent = `Week ${data.week}`;
            document.getElementById('week-select').value = data.week;
            document.getElementById('season-select').value = data.season;
        } catch (error) {
            console.error('Failed to load current week:', error);
        }
    }

    async loadSchedule() {
        try {
            const response = await fetch(`/api/schedule/${this.currentSeason}/${this.currentWeek}`);
            const games = await response.json();
            
            const gamesGrid = document.getElementById('games-grid');
            const scheduleWeek = document.getElementById('schedule-week');
            
            if (scheduleWeek) {
                scheduleWeek.textContent = `Week ${this.currentWeek}, ${this.currentSeason}`;
            }
            
            if (gamesGrid) {
                if (games.length === 0) {
                    gamesGrid.innerHTML = `
                        <div class="no-games">
                            <i class="fas fa-calendar-times"></i>
                            <p>No games scheduled for Week ${this.currentWeek}</p>
                        </div>
                    `;
                } else {
                    gamesGrid.innerHTML = games.map(game => this.createGameCard(game)).join('');
                }
            }
        } catch (error) {
            console.error('Failed to load schedule:', error);
            this.showError('Failed to load schedule');
        }
    }

    createGameCard(game) {
        const gameDate = game.date ? new Date(game.date).toLocaleDateString() : 'TBD';
        const gameTime = game.time || 'TBD';
        const completed = game.completed;
        const scoreDisplay = completed ? 
            `<div class="game-score">
                <span>${game.home_team}: ${game.home_score}</span>
                <span>${game.away_team}: ${game.away_score}</span>
            </div>` : '';
        
        return `
            <div class="game-card ${completed ? 'game-completed' : ''}">
                <div class="game-header">
                    <div class="game-time">${gameDate} ${gameTime}</div>
                </div>
                <div class="game-matchup">
                    <span class="team">${game.away_team}</span>
                    <span class="vs">@</span>
                    <span class="team">${game.home_team}</span>
                </div>
                ${scoreDisplay}
            </div>
        `;
    }

    async getPredictions() {
        this.showStatus('Generating predictions (this may take up to 20 minutes)...', 'loading');
        try {
            const response = await fetch(`/api/predictions/${this.currentSeason}/${this.currentWeek}/${this.currentScoring}`);
            const data = await response.json();
            if (response.ok) {
                this.displayPredictions(data);
                this.hideStatus();
                // Show dashboard
                document.getElementById('predictions-dashboard').style.display = 'block';
                document.getElementById('predictions-dashboard').scrollIntoView({ behavior: 'smooth', block: 'start' });
            } else {
                throw new Error(data.error || 'Failed to generate predictions');
            }
        } catch (error) {
            console.error('Failed to get predictions:', error);
            this.showError('Failed to generate predictions: ' + error.message);
        }
    }

    displayPredictions(data) {
        // Update summary cards
        this.updateSummaryCards(data);
        
        // Update optimal lineup
        this.updateOptimalLineup(data);
        
        // Update player rankings
        this.updatePlayerRankings(data);
        
        // Update DST recommendations
        this.updateDSTRecommendations(data);
        
        // Update injury count in header
        if (data.injury_report) {
            document.getElementById('injury-count').textContent = 
                data.injury_report.total_out + data.injury_report.total_questionable;
        }
    }

    updateSummaryCards(data) {
        if (data.summary) {
            document.getElementById('total-players').textContent = data.summary.total_players_analyzed || 0;
            document.getElementById('optimal-projection').textContent = 
                (data.summary.optimal_lineup_projection || 0).toFixed(1);
        }
        
        if (data.injury_report) {
            document.getElementById('injuries-out').textContent = data.injury_report.total_out || 0;
            document.getElementById('injuries-questionable').textContent = data.injury_report.total_questionable || 0;
        }
    }

    updateOptimalLineup(data) {
        const lineupGrid = document.getElementById('optimal-lineup');
        const lineupTotal = document.getElementById('lineup-total');
        
        if (data.optimal_lineup && lineupGrid) {
            lineupTotal.textContent = (data.optimal_lineup.total_projected || 0).toFixed(1);
            
            const positions = ['QB', 'RB', 'WR', 'TE'];
            lineupGrid.innerHTML = positions.map(position => {
                const players = data.optimal_lineup.players[position] || [];
                return `
                    <div class="lineup-position">
                        <div class="position-header">
                            <span class="position-name">${position}</span>
                        </div>
                        ${players.map(player => `
                            <div class="player-card">
                                <div class="player-info">
                                    <div class="player-name">${player.player_name}</div>
                                    <div class="player-team">${player.team_id}</div>
                                </div>
                                <div class="player-projection">${player.predicted_points.toFixed(1)}</div>
                            </div>
                        `).join('')}
                    </div>
                `;
            }).join('');
        }
    }

    updatePlayerRankings(data) {
        if (!data.top_players) return;
        
        // Initialize with QB rankings
        this.displayPositionRankings('QB', data.top_players);
        
        // Store data for tab switching
        this.rankingsData = data.top_players;
    }

    displayPositionRankings(position, topPlayers) {
        const rankingsContent = document.getElementById('rankings-content');
        const players = topPlayers[position] || [];
        
        if (rankingsContent) {
            rankingsContent.innerHTML = players.map((player, index) => `
                <div class="ranking-item">
                    <div class="rank-number">${index + 1}</div>
                    <div class="rank-player">
                        <div class="rank-name">${player.player_name}</div>
                        <div class="rank-team">${player.team_id} • ${player.position}</div>
                    </div>
                    <div class="rank-projection">${player.predicted_points.toFixed(1)}</div>
                    <div class="rank-confidence">${((player.confidence_score || 0.75) * 100).toFixed(0)}%</div>
                </div>
            `).join('') || '<div class="no-data">No players available</div>';
        }
    }

    updateDSTRecommendations(data) {
        const dstGrid = document.getElementById('dst-recommendations');
        const dstData = data.dst_recommendations || [];
        
        if (dstGrid) {
            dstGrid.innerHTML = dstData.slice(0, 8).map(dst => `
                <div class="dst-card">
                    <div class="dst-header">
                        <div class="dst-matchup">${dst.team_id} vs ${dst.opponent}</div>
                        <div class="dst-projection">${dst.adjusted_prediction.toFixed(1)}</div>
                    </div>
                    ${dst.injury_boost > 0 ? `<div class="dst-boost">+${(dst.injury_boost * 100).toFixed(0)}% injury boost</div>` : ''}
                    ${dst.opponent_key_injuries > 0 ? `<div class="dst-injuries">${dst.opponent_key_injuries} key injuries</div>` : ''}
                </div>
            `).join('') || '<div class="no-data">No DST recommendations available</div>';
        }
    }

    switchTab(position) {
        // Update active tab
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.position === position);
        });
        
        this.activeTab = position;
        
        // Display rankings for selected position
        if (this.rankingsData) {
            this.displayPositionRankings(position, this.rankingsData);
        }
    }

    async showInjuryReport() {
        this.showStatus('Loading injury report...', 'loading');
        
        try {
            const toggle = document.getElementById('historical-injury-toggle');
            const isHistorical = toggle ? toggle.checked : false;
            
            let response, data;
            
            if (isHistorical) {
                // Get current season/week selection
                const season = document.getElementById('season-select')?.value || new Date().getFullYear();
                const week = document.getElementById('week-select')?.value || 1;
                
                response = await fetch(`/api/injury-report/${season}/${week}`);
                data = await response.json();
            } else {
                response = await fetch('/api/injury-report');
                data = await response.json();
            }
            
            if (response.ok) {
                this.displayInjuryModal(data, isHistorical);
                this.hideStatus();
            } else {
                throw new Error(data.error || 'Failed to load injury report');
            }
        } catch (error) {
            console.error('Failed to load injury report:', error);
            this.showError('Failed to load injury report: ' + error.message);
        }
    }

    displayInjuryModal(data, isHistorical = false) {
        const modalBody = document.getElementById('injury-modal-body');
        const modalTitle = document.getElementById('injury-modal-title');
        
        // Update modal title
        if (modalTitle) {
            if (isHistorical && data.season && data.week) {
                modalTitle.textContent = `${data.season} Week ${data.week} Injury Report`;
            } else {
                modalTitle.textContent = 'Current Injury Report';
            }
        }
        
        if (modalBody) {
            const summaryHtml = `
                <div class="injury-summary">
                    <div class="injury-stat clickable active" data-filter="all" onclick="filterInjuries('all')">
                        <span class="injury-stat-value">${data.total_injuries}</span>
                        <span class="injury-stat-label">Total</span>
                    </div>
                    ${Object.entries(data.by_status).map(([status, count]) => `
                        <div class="injury-stat clickable" data-filter="${status.toLowerCase().replace(/\s+/g, '-')}" onclick="filterInjuries('${status}')">
                            <span class="injury-stat-value">${count}</span>
                            <span class="injury-stat-label">${status}</span>
                        </div>
                    `).join('')}
                </div>
            `;
            
            const detailsHtml = `
                <div class="injury-details">
                    ${data.details.map(injury => `
                        <div class="injury-item" data-status="${injury.status}">
                            <div class="injury-player">
                                <div class="injury-name">${injury.player_name}</div>
                                <div class="injury-team-pos">${injury.team} • ${injury.position}</div>
                            </div>
                            <div class="injury-status-column">
                                <div class="injury-status ${injury.status.toLowerCase().replace(/\s+/g, '-')}">${injury.status}</div>
                            </div>
                            <div class="injury-type-column">
                                <div class="injury-type">${injury.injury_type}</div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
            
            modalBody.innerHTML = summaryHtml + detailsHtml;
        }
        
        this.showModal('injury-modal');
    }

    async updateData() {
        this.showStatus('Updating database...', 'loading');
        
        try {
            const response = await fetch('/api/update-data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ seasons: [2024, 2025], update_schedules: true, update_injuries: true, update_dst: true })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                const inc = data.includes || {};
                const items = [];
                if (inc.schedules) items.push('schedules');
                if (inc.injuries) items.push('injuries');
                if (inc.dst_stats) items.push('DST stats');
                const seasons = (inc.seasons || []).join(', ');
                const detail = items.length ? `Updating ${items.join(', ')}${seasons ? ` for seasons ${seasons}` : ''}...` : 'Data update started in background...';
                this.showStatus(detail, 'success');
                setTimeout(() => this.hideStatus(), 3000);
            } else {
                throw new Error(data.error || 'Failed to update data');
            }
        } catch (error) {
            console.error('Failed to update data:', error);
            this.showError('Failed to update data: ' + error.message);
        }
    }

    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('active');
        }
    }

    closeModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('active');
        }
    }

    showStatus(message, type = 'info') {
        const statusBar = document.getElementById('status-bar');
        const statusMessage = document.getElementById('status-message');
        
        if (statusBar && statusMessage) {
            statusMessage.textContent = message;
            statusBar.style.display = 'block';
            
            // Update icon based on type
            const icon = statusBar.querySelector('i');
            if (icon) {
                icon.className = type === 'loading' ? 'fas fa-spinner fa-spin' :
                                type === 'success' ? 'fas fa-check-circle' :
                                type === 'error' ? 'fas fa-exclamation-circle' :
                                'fas fa-info-circle';
            }
            
            // Update color based on type
            statusBar.className = `status-bar status-${type}`;
        }
    }

    hideStatus() {
        const statusBar = document.getElementById('status-bar');
        if (statusBar) {
            statusBar.style.display = 'none';
        }
    }

    showError(message) {
        this.showStatus(message, 'error');
        setTimeout(() => this.hideStatus(), 5000);
    }

    updateLastUpdated() {
        const lastUpdated = document.getElementById('last-updated');
        if (lastUpdated) {
            lastUpdated.textContent = new Date().toLocaleString();
        }
    }
    
    setupHistoricalToggle() {
        const toggle = document.getElementById('historical-injury-toggle');
        if (toggle) {
            // Add event listener for checkbox changes
            toggle.addEventListener('change', () => {
                this.updateDropdownAvailability();
            });
            
            // Initialize dropdown availability
            this.updateDropdownAvailability();
        }
    }
    
    updateDropdownAvailability() {
        const toggle = document.getElementById('historical-injury-toggle');
        const seasonSelect = document.getElementById('season-select');
        const weekSelect = document.getElementById('week-select');
        
        if (!toggle || !seasonSelect || !weekSelect) return;
        
        const currentYear = new Date().getFullYear();
        const isHistoricalMode = toggle.checked;
        
        if (isHistoricalMode) {
            // Historical mode: enable all options
            for (let option of seasonSelect.options) {
                option.disabled = false;
            }
            for (let option of weekSelect.options) {
                option.disabled = false;
            }
        } else {
            // Current mode: disable past years and reset to current
            for (let option of seasonSelect.options) {
                const year = parseInt(option.value);
                if (year < currentYear) {
                    option.disabled = true;
                }
            }
            
            // Reset to current year if a past year is selected
            if (parseInt(seasonSelect.value) < currentYear) {
                seasonSelect.value = currentYear;
                // Trigger change event to update week options
                seasonSelect.dispatchEvent(new Event('change'));
            }
            
            // Disable past weeks for current year (simplified - assumes current is early in season)
            const currentWeek = Math.min(Math.max(Math.ceil(((new Date() - new Date(currentYear, 8, 5)) / (1000 * 60 * 60 * 24)) / 7), 1), 18);
            for (let option of weekSelect.options) {
                const week = parseInt(option.value);
                if (parseInt(seasonSelect.value) === currentYear && week < currentWeek - 1) {
                    option.disabled = true;
                }
            }
            
            // Reset to current week if past week selected
            if (parseInt(seasonSelect.value) === currentYear && parseInt(weekSelect.value) < currentWeek - 1) {
                weekSelect.value = Math.max(currentWeek - 1, 1);
            }
        }
    }
    
    async checkInitializationStatus() {
        try {
            const response = await fetch('/api/initialization-status');
            const data = await response.json();
            
            const initButton = document.getElementById('initialize-database');
            const otherButtons = document.querySelectorAll('#get-predictions, #refresh-injuries, #update-data');
            
            if (data.initialized) {
                // Hide initialize button, show other buttons
                if (initButton) initButton.style.display = 'none';
                otherButtons.forEach(btn => {
                    if (btn) btn.style.display = 'inline-flex';
                });
            } else {
                // Show initialize button, hide other buttons
                if (initButton) initButton.style.display = 'inline-flex';
                otherButtons.forEach(btn => {
                    if (btn) btn.style.display = 'none';
                });
            }
        } catch (error) {
            console.error('❌ Error checking initialization status:', error);
        }
    }
    
    async initializeDatabase() {
        const button = document.getElementById('initialize-database');
        
        try {
            // Update button to show processing
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Initializing...';
            button.disabled = true;
            
            this.showStatus('Starting database initialization...', 'info');
            
            const response = await fetch('/api/initialize-database', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({})
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            if (result.status === 'success') {
                this.showStatus('Database initialization started successfully! This may take several minutes...', 'success');
                
                // Poll for completion
                setTimeout(() => this.pollInitializationStatus(), 5000);
                
            } else {
                throw new Error(result.message || 'Unknown error');
            }
        } catch (error) {
            console.error('❌ Error initializing database:', error);
            this.showStatus(`Error initializing database: ${error.message}`, 'error');
            
            // Reset button
            button.innerHTML = '<i class="fas fa-rocket"></i> Initialize Database';
            button.disabled = false;
        }
    }
    
    async pollInitializationStatus() {
        try {
            const response = await fetch('/api/initialization-status');
            const data = await response.json();
            
            if (data.initialized) {
                this.showStatus('Database initialization completed successfully!', 'success');
                
                // Hide the initialize button and show other controls
                await this.checkInitializationStatus();
                
                // Reload page data
                await this.loadInitialData();
                
            } else {
                // Continue polling
                setTimeout(() => this.pollInitializationStatus(), 10000);
            }
        } catch (error) {
            console.error('❌ Error polling initialization status:', error);
            setTimeout(() => this.pollInitializationStatus(), 10000);
        }
    }
}

// Global function for injury filtering
window.filterInjuries = function(status) {
    // Update active status in summary
    const stats = document.querySelectorAll('.injury-stat');
    stats.forEach(stat => stat.classList.remove('active'));
    
    if (status === 'all') {
        document.querySelector('.injury-stat[data-filter="all"]').classList.add('active');
    } else {
        document.querySelector(`.injury-stat[data-filter="${status.toLowerCase().replace(/\s+/g, '-')}"]`).classList.add('active');
    }
    
    // Filter injury items
    const items = document.querySelectorAll('.injury-item');
    items.forEach(item => {
        if (status === 'all' || item.dataset.status === status) {
            item.style.display = 'grid';
        } else {
            item.style.display = 'none';
        }
    });
};

// Global functions for modal handling
window.closeModal = function(modalId) {
    if (window.app) {
        window.app.closeModal(modalId);
    }
};

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new NFLFantasyApp();
});

// Add some nice loading animations and utilities
class UIUtils {
    static createLoadingSpinner() {
        return '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i></div>';
    }
    
    static formatNumber(num, decimals = 1) {
        return Number(num).toFixed(decimals);
    }
    
    static formatDate(dateString) {
        return new Date(dateString).toLocaleDateString();
    }
    
    static fadeIn(element, duration = 300) {
        element.style.opacity = '0';
        element.style.display = 'block';
        
        let start = null;
        function animate(timestamp) {
            if (!start) start = timestamp;
            const progress = timestamp - start;
            const opacity = Math.min(progress / duration, 1);
            
            element.style.opacity = opacity;
            
            if (progress < duration) {
                requestAnimationFrame(animate);
            }
        }
        
        requestAnimationFrame(animate);
    }
    
    static slideDown(element, duration = 300) {
        element.style.height = '0px';
        element.style.overflow = 'hidden';
        element.style.display = 'block';
        
        const targetHeight = element.scrollHeight + 'px';
        
        let start = null;
        function animate(timestamp) {
            if (!start) start = timestamp;
            const progress = timestamp - start;
            const height = Math.min(progress / duration, 1) * parseInt(targetHeight);
            
            element.style.height = height + 'px';
            
            if (progress < duration) {
                requestAnimationFrame(animate);
            } else {
                element.style.height = '';
                element.style.overflow = '';
            }
        }
        
        requestAnimationFrame(animate);
    }
}

// Export for use in other modules
window.UIUtils = UIUtils;
