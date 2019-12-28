import getConfig from 'next/config'
const { publicRuntimeConfig } = getConfig();

function Index() {
    let sign_in_url = "https://" + publicRuntimeConfig.backendDomain + "/login";
    return (
        <div>
            <img src="/img/logo.png" alt="Semiphemeral" />
            <p><a href={sign_in_url}>Sign in with Twitter</a></p>
            <style jsx>{`
                div {
                    text-align: center;
                }
                p {
                    font-family: sans-serif;
                }
                a {
                    color: #343877;
                    text-decoration: none;
                }
            `}</style>
        </div>
    )
}

export default Index