Vue.component('nav-button', {
    props: ["currentPageComponent", "buttonText", "pageComponent"],
    computed: {
        isActive: function () {
            return this.currentPageComponent == this.pageComponent
        }
    },
    template: `
        <button
            v-on:click="$emit('select-page')"
            v-bind:class="{ active: isActive }">
            {{ buttonText }}
        </button>
    `
})

Vue.component('nav-bar', {
    props: ['currentPageComponent'],
    data: function () {
        return {
            buttons: [
                { buttonText: "Dashboard", pageComponent: "dashboard" },
                { buttonText: "Tweets", pageComponent: "tweets" },
                { buttonText: "Settings", pageComponent: "settings" },
                { buttonText: "Tip", pageComponent: "tip" },
            ]
        }
    },
    template: `
        <div class="nav">
            <span class="logo"><a href="/"><img src="/static/img/logo-small.png" /></a></span>
            <ul>
                <li v-for="button in buttons">
                    <nav-button
                        v-bind="{
                            currentPageComponent: currentPageComponent,
                            buttonText: button.buttonText,
                            pageComponent: button.pageComponent
                        }"
                        v-on:select-page="$emit('select-page', button.pageComponent)">
                    </nav-button>
                </li>
            </ul>
            <span class="user">@twitter_user</span>
        </div>
    `,

})

var app = new Vue({
    el: "#app",
    data: {
        currentPageComponent: "dashboard"
    },
    methods: {
        selectPage: function (pageComponent) {
            this.currentPageComponent = pageComponent
        }
    }
})