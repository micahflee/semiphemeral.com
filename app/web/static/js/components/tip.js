Vue.component('tip', {
    data: function () {
        return {
            loading: false,
            stripePublishableKey: false,
            amount: "5",
            otherAmount: ""
        }
    },
    created: function () {
        var that = this;
        fetch("/api/tip")
            .then(function (response) {
                if (response.status !== 200) {
                    console.log('Error fetching tip variables, status code: ' + response.status);
                    return;
                }
                response.json().then(function (data) {
                    that.stripePublishableKey = data['stripe_publishable_key'];
                    that.initStripe()
                })
            })
            .catch(function (err) {
                console.log("Error fetching tip variables", err)
            })
    },
    methods: {
        initStripe: function () {
            // Initialize Stripe
            var stripe = Stripe(this.stripePublishableKey);
            var elements = stripe.elements();

            // Create a card element, attach it to the div
            var card = elements.create('card');
            card.mount('#card-element');

            // Create a token or display an error when the form is submitted
            var form = document.getElementById('payment-form');
            form.addEventListener('submit', function (event) {
                event.preventDefault();

                stripe.createToken(card).then(function (result) {
                    if (result.error) {
                        // Inform the customer that there was an error
                        var errorElement = document.getElementById('card-errors');
                        errorElement.textContent = result.error.message;
                    } else {
                        // Send the token to the server
                        var token = result.token;

                        // Insert the token ID into the form so it gets submitted to the server
                        var form = document.getElementById('payment-form');
                        var hiddenInput = document.createElement('input');
                        hiddenInput.setAttribute('type', 'hidden');
                        hiddenInput.setAttribute('name', 'stripeToken');
                        hiddenInput.setAttribute('value', token.id);
                        form.appendChild(hiddenInput);

                        // Submit the form
                        form.submit();
                    }
                });
            });
        }
    },
    template: `
        <div class="page tip">
            <h1>Care to chip in?</h1>
            <p>Semiphemeral is free. Every day a bot will automatically delete your old tweets and likes except for the ones you want to keep, keeping your social media presence a bit more private. Hosting this service costs money though, so tips are appreciated.</p>

            <p>As long as you're using this service, the @semiphemeral Twitter account will gently ask you for a tip, via Twitter DM, once a month. If you donate any amount, even just $1, it will stop nagging you for a year.</p>

            <form action="/api/tip" method="post" id="payment-form">
                <fieldset>
                    <legend>How much would you like to tip?</legend>
                    <ul>
                        <li><label><input type="radio" name="amount" value="1" v-model="amount" /> $1</label></li>
                        <li><label><input type="radio" name="amount" value="2" v-model="amount" /> $2</label></li>
                        <li><label><input type="radio" name="amount" value="5" v-model="amount" /> $5</label></li>
                        <li><label><input type="radio" name="amount" value="10" v-model="amount" /> $10</label></li>
                        <li><label><input type="radio" name="amount" value="50" v-model="amount" /> $50</label></li>
                        <li>
                            <label><input type="radio" name="amount" value="other" v-model="amount" /> Other</label>
                            <span v-if="amount == 'other'">$<input type="text" v-model.number="otherAmount" class="other-amount" /></span>
                        </li>
                    </ul>
                </fieldset>
                <fieldset>
                    <legend>Credit or debit card</legend>
                    <div id="card-element"></div>
                    <div id="card-errors" role="alert"></div>
                </fieldset>

                <p>
                    <input v-bind:disabled="loading" type="submit" value="Tip" />
                    <img v-if="loading" src="/static/img/loading.gif" alt="Loading" />
                </p>
            </form>
        </div>
    `
})