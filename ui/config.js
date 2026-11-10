// Base URLs of the two services. Locally these point at the compose ports;
// on Azure the pipeline overwrites this file with the Container Apps URLs.
window.APP_CONFIG = {
  BATCHES_URL: "http://localhost:8001",
  FEEDBACK_URL: "http://localhost:8002",
};
