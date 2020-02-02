<template>
  <div>
    <span class="logo">
      <a href="/">
        <img src="/static/img/logo-small.png" />
      </a>
    </span>
    <ul>
      <li v-for="button in buttons">
        <NavButton
          v-bind="{
                            currentPageComponent: currentPageComponent,
                            buttonText: button.buttonText,
                            pageComponent: button.pageComponent
                        }"
          v-on:select-page="$emit('select-page', button.pageComponent)"
        ></NavButton>
      </li>
    </ul>
    <span class="user">
      <img v-if="userScreenName" v-bind:src="userProfileUrl" v-bind:title="logoutTitle" />
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

span.user {
  display: block;
  float: right;
}

span.user img {
  width: 30px;
  border-radius: 50%;
  vertical-align: middle;
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

<script>
import NavButton from "./NavButton.vue";

export default {
  props: ["currentPageComponent", "userScreenName", "userProfileUrl"],
  data: function() {
    return {
      buttons: [
        { buttonText: "Dashboard", pageComponent: "Dashboard" },
        { buttonText: "Tweets", pageComponent: "Tweets" },
        { buttonText: "Settings", pageComponent: "Settings" },
        { buttonText: "Tip", pageComponent: "Tip" }
      ]
    };
  },
  computed: {
    logoutTitle: function() {
      return "Logged in as @" + this.userScreenName;
    }
  },
  components: {
    NavButton: NavButton
  }
};
</script>