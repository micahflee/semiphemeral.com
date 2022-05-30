<script>
export default {
  props: ["userScreenName"],
  data: function () {
    return {};
  },
};
</script>

<template>
  <div>
    <h1>Frequently Asked Questions</h1>

    <h2>What if something is broken?</h2>
    <p>
      Semiphemeral is still a beta service. If something isn't working like it should, or is confusing, please report it. You can send a Twitter message to
      <a
        href="https://twitter.com/semiphemeral"
        target="_blank"
      >@semiphemeral</a>.
    </p>

    <h2>Why aren't tweets showing up on the tweets page?</h2>
    <p>The tweets page should embed all of the tweets that will get automatically deleted the next time it's your turn to delete. If you just created your account, you need to wait for your tweets to finish downloading the first time first.</p>
    <p>If you've already finished downloading tweets and they're still not getting displayed, this is probably because your web browser is blocking them. Do you have browser extensions like Privacy Badger, or is Firefox's tracking protection blocking the script from twitter.com? Try disabling those thing for semiphemeral.com, and the tweets should get displayed.</p>

    <h2>Why is Semiphemeral only deleting my most recent 3,000 tweets?</h2>
    <p>Twitter's API works in mysterious ways. For some users, when you tell the API "give me a list of all of my tweets", it only gives about 3,000 tweets, but for others it returns all of their tweets. Unfortunately there doesn't seem to be anything that Semiphemeral can do about this.</p>
    <p>If Semiphemeral isn't successfully deleting your very old tweets, you can try manually deleting those tweets yourself, and then rely on Semiphemal to automatically delete tweets going forward.</p>

    <h2>Why did Semiphemeral only unlike about 4,000 of my likes?</h2>
    <p>
      <a
        href="https://github.com/micahflee/semiphemeral#deleting-old-likes"
      >One does not simply unlike old tweets.</a> For some reason, when Semiphemeral asks the Twitter API for a list of all of your likes, it sometimes only returns a list of the most recent 4,000 likes, even if your profile says you have way more than that.
    </p>
    <p>
      If you go and find those old tweets that you liked over 4,000 likes ago, you can't unlike them manually either. The only way to actually remove those likes is to
      <em>re-like them and then unlike them again</em>, which is extremely noisy because everyone will get notified each time you re-like their old tweets. Because of this, Semiphemeral doesn't support deleting those old likes. But if you really want to (and you're enough of a tech nerd) you can do this using the self-hosted
      <a
        href="https://github.com/micahflee/semiphemeral"
      >open source semiphemeral project</a>.
    </p>

    <h2>Can I tell my friends?</h2>
    <p>Yes! This is a free service and everyone is welcome to use it so long as they don't support fascists (who will get automatically detected and blocked).</p>
  </div>
</template>