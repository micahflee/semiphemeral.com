<script setup>
const props = defineProps({
  userScreenName: String,
  userProfileUrl: String,
  canSwitch: Boolean
})

function switchBack() {
  fetch("/admin_api/users/impersonate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      twitter_id: "0",
    }),
  })
    .then(function (response) {
      if (confirm("Reload?")) {
        window.location.reload(true)
      }
    })
    .catch(function (err) {
      console.log("Error", err)
    })
}
</script>

<template>
  <div>
    <span class="logo">
      <a href="/">
        <img src="/images/logo-small.png" />
      </a>
    </span>
    <ul>
      <li>
        <router-link to="/dashboard">Dashboard</router-link>
      </li>
      <li>
        <router-link to="/tweets">Tweets</router-link>
      </li>
      <li>
        <router-link to="/export">Export</router-link>
      </li>
      <li>
        <router-link to="/dms">DMs</router-link>
      </li>
      <li>
        <router-link to="/settings">Settings</router-link>
      </li>
      <li>
        <router-link to="/tip">Tip</router-link>
      </li>
      <li>
        <router-link to="/faq">FAQ</router-link>
      </li>
    </ul>
    <span class="user">
      <button v-if="canSwitch" @click="switchBack()">switch back</button>
      <img v-if="userScreenName" :src="userProfileUrl" :title="`Logged in as @${userScreenName}`" />
      <span>
        <a href="/auth/logout">Log out</a>
      </span>
    </span>
  </div>
</template>

<style scoped>
span.logo img {
  vertical-align: middle;
  border: 0;
}

ul {
  display: inline-block;
  list-style: none;
  margin: 0;
  padding: 0;
  vertical-align: middle;
}

ul li {
  display: inline-block;
  padding: 3px 10px;
}

ul li a {
  border: 0;
  background-color: transparent;
  padding: 5px;
  text-decoration: none;
}

ul li a.router-link-active {
  color: #42465d;
  border-bottom: 3px solid #42465d;
}

span.user {
  display: block;
  float: right;
}

span.user img {
  width: 30px;
  border-radius: 50%;
  vertical-align: middle;
  margin-left: 0.5em;
  margin-right: 0.5em;
}

span.user span {
  vertical-align: middle;
  font-size: 0.8em;
}

span.user span a {
  color: #42465d;
  text-decoration: none;
}
</style>