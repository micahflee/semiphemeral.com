Vue.component('app-nav', {
    template: `
        <div class="nav">
            <span class="logo"><a href="/"><img src="/static/img/logo-small.png" /></a></span>
            <ul>
                <li>Dashboard</li>
                <li>Tweets</li>
                <li>Settings</li>
                <li>Tip</li>
            </ul>
            <span class="user">@twitter_user</span>
        </div>
    `
})