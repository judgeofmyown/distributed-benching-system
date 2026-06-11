import './style.css'
import Alpine from 'alpinejs'

window.Alpine = Alpine

window.dashboardApp = function() {
    return {
        activeTab: 'workspace',
        file: null,
        uploading: false,
        uploadMessage: '',
        uploadError: '',

        leaderboard: [],
        performance: {},

        fileSelected(e) {
            this.file = e.target.files[0];
        },
        
        async uploadFile() {
            if (!this.file) return;

            this.uploading = true;
            this.uploadMessage = '';
            this.uploadError = '';

            const formData = new FormData();
            formData.append('file', this.file);
            
            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) throw new Error('Cluster processing routing encountered an error runtime fault.');
                
                this.uploadMessage = 'Payload submitted! fetching updated engine telemetry ...';
                this.file = null;
                document.getElementById('fileInput').value = '';

                await this.fetchPerformance();
                this.uploadMessage = 'Telemetry updated successfully.';
            } catch (err) {
                this.uploadError = err.message;
            } finally {
                this.uploading = false;
            }
        },

        async fetchLeaderboard() {
            try {
                const response = await fetch('/api/leaderboard');
                if (!response.ok) throw new Error('Could not resolve core standings data.');
                this.leaderboard = await response.json();
            } catch (err) {
                console.error("Leaderboard pipeline fault: ", err);
            }
        },

        async fetchPerformance() {
            try {
                const response = await fetch('/api/performance');
                if (!response.ok) throw new Error('Telemetry databse dropped parsing loop.');
                this.performance = await response.json();
            } catch(err) {
                console.error("Profiling data pipeline fault: ", err);
            }
        }
    }
}

Alpine.start()
