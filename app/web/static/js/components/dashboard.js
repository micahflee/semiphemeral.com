Vue.component('dashboard', {
    data: function () {
        return {
            loading: false,
            activeJobs: [],
            pendingJobs: []
        }
    },
    created: function () {
        this.fetchJobs()
    },
    methods: {
        startSemiphemeral: function () {
            var that = this;
            this.loading = true;
            fetch("/api/job", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "start" })
            })
                .then(function (response) {
                    that.fetchJobs()
                })
                .catch(function (err) {
                    console.log("Error starting semiphemeral", err)
                    that.loading = false;
                })
        },
        pauseSemiphemeral: function () {
            var that = this;
            this.loading = true;
            fetch("/api/job", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "pause" })
            })
                .then(function (response) {
                    that.fetchJobs()
                })
                .catch(function (err) {
                    console.log("Error pausing semiphemeral", err)
                    that.loading = false;
                })
        },
        fetchJobs: function () {
            var that = this;
            this.loading = true;

            // Get list of pending and active jobs
            fetch("/api/job")
                .then(function (response) {
                    if (response.status !== 200) {
                        console.log('Error fetching jobs, status code: ' + response.status);
                        that.loading = false;
                        return;
                    }
                    response.json().then(function (data) {
                        that.loading = false;
                        if (data['active_jobs'])
                            that.activeJobs = data['active_jobs'];
                        else
                            that.activeJobs = [];

                        if (data['pending_jobs'])
                            that.pendingJobs = data['pending_jobs'];
                        else
                            that.pendingJobs = [];
                    })
                })
                .catch(function (err) {
                    console.log("Error fetching jobs", err)
                    that.loading = false;
                })
        }
    },
    template: `
        <div class="page dashboard">
            <h1>Semiphemeral Dashboard</h1>

            <p v-if="loading"><img src="/static/img/loading.gif" alt="Loading" /></p>

            <div v-if="!loading && activeJobs.length == 0 && pendingJobs.length == 0">
                Semiphemeral is <strong>paused</strong>. When you're sure that your
                <button v-on:click="$emit('select-page', 'settings')">settings</button>
                are exactly as you want them:
                <button v-on:click="startSemiphemeral">Start Semiphemeral</button>
            </div>

            <div v-if="!loading && (activeJobs.length > 0 || pendingJobs.length > 0)">
                Semiphemeral is <strong>active</strong>.
                <button v-on:click="pauseSemiphemeral">Pause Semiphemeral</button>
            </div>
        </div>
    `
})