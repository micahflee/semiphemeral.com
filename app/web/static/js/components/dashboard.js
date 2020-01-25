Vue.component('job', {
    props: ["job"],
    computed: {
        scheduledTimestampInThePast: function () {
            // job['scheduled_timestamp']
        },
        humanReadableScheduledTimestamp: function () {
            // job['scheduled_timestamp']
        }
    },
    template: `
        <div v-bind:class="job.status">
            <template v-if="job.type == 'fetch'">
                <template v-if="job.status == 'pending'">
                    <p v-if="scheduledTimestampInThePast">Waiting to download all of your tweets and likes as soon as it's your turn in the queue.</p>
                    <p v-else>Waiting to download all of your tweets and likes, scheduled for <em>{{ humanReadableScheduledTimestamp }}</em>.</p>
                </template>
                <template v-else>
                    <p>Downloading all of your tweets and likes. Progress: <span class="project">{{ job.progress }}</span></p>
                </template>
            </template>

            <template v-if="job.type == 'delete'">
                <template v-if="job.status == 'pending'">
                    <p v-if="scheduledTimestampInThePast">Waiting to delete your old tweets and likes as soon as it's your turn in the queue.</p>
                    <p v-else>Waiting to delete your old tweets and likes, scheduled for <em>{{ humanReadableScheduledTimestamp }}</em>.</p>
                </template>
                <template v-else>
                    <p>Deleting your tweets and likes. Progress: <span class="project">{{ job.progress }}</span></p>
                </template>
            </template>
        </div>
    `
})

Vue.component('dashboard', {
    data: function () {
        return {
            loading: false,
            paused: null,
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

                        that.paused = data['paused'];
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

            <div v-if="!loading && paused">
                <p>Semiphemeral is <strong>paused</strong>. Before starting Semiphemeral:</p>
                <ol>
                    <li>
                        Make sure your
                        <button v-on:click="$emit('select-page', 'settings')">settings</button>
                        are exactly as you want them
                    </li>
                    <li>
                        Make sure you have manually chosen which of your old
                        <button v-on:click="$emit('select-page', 'tweets')">tweets</button>
                        you want to make sure don't get automatically deleted
                    </li>
                </ol>
                <p v-if="pendingJobs.length == 0 and activeJobs.length == 0">
                    <button v-on:click="startSemiphemeral">Start Semiphemeral</button>
                </p>
                <p v-else>
                    <em>You must wait for Semiphemeral to finish download all your old tweets
                    before you can start deleting, so you don't accidentally delete tweets
                    you wished you had kept.</em>
                </p>
            </div>

            <div v-if="!loading && !paused">
                <p>
                    Semiphemeral is <strong>active</strong>.
                    <button v-on:click="pauseSemiphemeral">Pause Semiphemeral</button>
                </p>
            </div>

            <ul v-if="activeJobs.length > 0" v-for="job in activeJobs">
                <job v-bind:job="job"></job>
            </ul>

            <ul v-if="pendingJobs.length > 0" v-for="job in pendingJobs">
                <job v-bind:job="job"></job>
            </ul>
        </div>
    `
})