package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;
import java.net.URI;
import java.net.http.HttpRequest;

// Analysis fixture: no Java or Spring runtime is needed to scan this file.
@RestController
@RequestMapping("/api")
public class WeatherController {
    private final RestTemplate rest;

    @Value("${notify.url}")
    private String notifyUrl;

    public WeatherController(RestTemplate rest) {
        this.rest = rest;
    }

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @PostMapping("/notify")
    public void notifyRemote() {
        rest.postForEntity(notifyUrl, null, String.class);
    }

    public HttpRequest auditRequest() {
        final String endpoint = "https://audit.example.com" + "/events";
        return HttpRequest.newBuilder(URI.create(endpoint)).GET().build();
    }
}
