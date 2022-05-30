<style scoped>
label {
  display: inline-block;
  width: 100px;
  text-align: right;
  margin-right: 10px;
}

input[type="text"] {
  width: 300px;
}

ul {
  padding: 0;
  list-style: none;
}
</style>

<template>
  <div>
    <h1>Fascists</h1>
    <template v-if="loading">
      <p>
        <img src="/static/img/loading.gif" alt="Loading" />
      </p>
    </template>
    <template v-else>
      <form v-on:submit.prevent="onCreateSubmit">
        <fieldset>
          <legend>Add fascist</legend>
          <p>
            <label for="username">Username</label>
            <input
              type="text"
              placeholder="TuckerCarlson"
              name="username"
              ref="username"
            />
          </p>
          <p>
            <label for="comment">Comment</label>
            <input
              type="text"
              placeholder="US white nationalist propagandist"
              name="comment"
              ref="comment"
            />
          </p>
          <p>
            <input v-bind:disabled="loading" type="submit" value="Add" />
          </p>
        </fieldset>
      </form>

      <ul>
        <li v-for="(fascist, index) in fascists" v-bind:key="index">
          <Fascist
            v-bind:fascist="fascist"
            v-on:reload="fetchFascists()"
          ></Fascist>
        </li>
      </ul>
    </template>
  </div>
</template>

<script>
import Fascist from "./Fascists/Fascist.vue";

export default {
  props: ["userScreenName"],
  data: function () {
    return {
      loading: false,
      fascists: [],
    };
  },
  created: function () {
    this.fetchFascists();
  },
  methods: {
    onCreateSubmit: function () {
      var that = this;
      this.loading = true;
      fetch("/admin_api/fascists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "create",
          username: this.$refs.username.value,
          comment: this.$refs.comment.value,
        }),
      })
        .then(function (response) {
          that.fetchFascists();
        })
        .catch(function (err) {
          console.log("Error", err);
          that.loading = false;
        });
    },
    fetchFascists: function () {
      var that = this;
      this.loading = true;

      // Get lists of users
      fetch("/admin_api/fascists")
        .then(function (response) {
          if (response.status !== 200) {
            console.log(
              "Error fetching fascists, status code: " + response.status
            );
            that.loading = false;
            return;
          }
          response.json().then(function (data) {
            that.loading = false;
            if (data["fascists"]) that.fascists = data["fascists"];
            else that.fascists = [];
          });
        })
        .catch(function (err) {
          console.log("Error fetching users", err);
          that.loading = false;
        });
    },
  },
  components: {
    Fascist: Fascist,
  },
};
</script>