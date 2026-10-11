// labPBR 1.3 material decoding and the shared lighting model.

struct Material {
    vec3 albedo;      // linear
    float smoothness;
    float f0raw;      // 0..255 green channel
    vec3 f0;
    bool metal;
    float porosity;
    float sss;
    float emission;
    float ao;
};

vec3 metalF0(int id, vec3 albedo) {
    vec3 f;
    if      (id == 230) f = vec3(0.56, 0.57, 0.58); // iron
    else if (id == 231) f = vec3(1.00, 0.78, 0.34); // gold
    else if (id == 232) f = vec3(0.91, 0.92, 0.92); // aluminium
    else if (id == 233) f = vec3(0.55, 0.56, 0.55); // chrome
    else if (id == 234) f = vec3(0.95, 0.64, 0.54); // copper
    else if (id == 235) f = vec3(0.63, 0.62, 0.60); // lead
    else if (id == 236) f = vec3(0.67, 0.64, 0.59); // platinum
    else if (id == 237) f = vec3(0.95, 0.93, 0.88); // silver
    else return albedo;                            // 238..255: albedo is F0
    // labPBR: albedo tints the reflections of predefined metals
    vec3 tint = albedo / max(max(albedo.r, max(albedo.g, albedo.b)), 0.05);
    return f * mix(vec3(1.0), tint, 0.5);
}

Material decodeMaterial(vec4 albedoSRGB, vec4 spec, float ao) {
    Material m;
    m.albedo = toLinear(albedoSRGB.rgb);
    m.ao = ao;
#ifdef SPECULAR_MAPPING
    m.smoothness = spec.r;
    m.f0raw = spec.g * 255.0;
    m.metal = m.f0raw > 229.5;
    m.f0 = m.metal ? metalF0(int(m.f0raw + 0.5), m.albedo) : vec3(spec.g);
    float b = spec.b * 255.0;
    m.porosity = b <= 64.5 ? b / 64.0 : 0.0;
    m.sss = b > 64.5 ? (b - 65.0) / 190.0 : 0.0;
    m.emission = spec.a < 0.999 ? spec.a : 0.0;
#else
    m.smoothness = 0.0;
    m.f0raw = 10.0;
    m.metal = false;
    m.f0 = vec3(0.04);
    m.porosity = 0.0;
    m.sss = 0.0;
    m.emission = 0.0;
#endif
    return m;
}

vec3 fresnelSchlick(float cosTheta, vec3 f0) {
    return f0 + (1.0 - f0) * pow(1.0 - saturate(cosTheta), 5.0);
}

// GGX specular lobe (already multiplied by NdotL)
vec3 specularGGX(vec3 N, vec3 V, vec3 L, float roughness, vec3 f0) {
    vec3 H = normalize(L + V);
    float NdotL = saturate(dot(N, L));
    float NdotV = max(dot(N, V), 1e-3);
    float NdotH = saturate(dot(N, H));
    float a = max(roughness * roughness, 0.002);
    float a2 = a * a;
    float d = NdotH * NdotH * (a2 - 1.0) + 1.0;
    float D = a2 / (PI * d * d);
    float k = sq(roughness + 1.0) / 8.0;
    float G = (NdotV / (NdotV * (1.0 - k) + k)) * (NdotL / (NdotL * (1.0 - k) + k));
    vec3 F = fresnelSchlick(dot(H, V), f0);
    return min(D * G * F / (4.0 * NdotV), vec3(40.0)) * NdotL;
}

vec3 blockLightColor(float lm) {
    float l = pow(lm, 4.0) * 1.1 + pow(lm, 12.0) * 1.6;
    return vec3(1.0, 0.56, 0.26) * l * BLOCKLIGHT_INTENSITY;
}

// Wet surfaces in rain: darker porous albedo and glossy puddles on upward faces
void applyWetness(inout Material m, vec3 worldPos, vec3 normalW, float skyLight) {
#if defined WET_SURFACES && !defined DIM_NETHER && !defined DIM_END
    float wet = wetness * smoothstep(0.85, 0.95, skyLight);
    if (wet < 0.001) return;
    float up = smoothstep(0.6, 0.95, normalW.y);
    float puddle = smoothstep(0.45, 0.65, vnoise(worldPos.xz * 0.35) * 0.7 + vnoise(worldPos.xz * 1.3) * 0.3);
    // no puddles on grass, leaves, snow and other subsurface materials
    puddle *= up * wet * (1.0 - smoothstep(0.0, 0.1, m.sss));
    m.albedo *= 1.0 - m.porosity * wet * 0.45;
    m.smoothness = mix(m.smoothness, 0.75, wet * 0.6 * (0.3 + 0.7 * up) * (1.0 - m.sss));
    m.smoothness = mix(m.smoothness, 0.97, puddle);
    if (!m.metal) m.f0 = mix(m.f0, vec3(0.02), puddle);
#endif
}

// N: shading normal (view), Nflat: geometric normal (view), viewPos: fragment view position
vec3 shade(Material m, vec3 N, vec3 Nflat, vec3 viewPos, vec2 lm, float pomShadow, int matId, float noise) {
    vec3 V = -normalize(viewPos);
    vec3 L = normalize(shadowLightPosition);
    vec3 playerPos = mat3(gbufferModelViewInverse) * viewPos + gbufferModelViewInverse[3].xyz;
    vec3 normalW = mat3(gbufferModelViewInverse) * Nflat;

    float NdotL = dot(N, L);
    float flatNdotL = dot(Nflat, L);
    bool foliage = matId == MAT_FOLIAGE;
    float sss = max(m.sss, foliage ? 0.55 : 0.0) * SSS_STRENGTH;

    vec3 lightCol = directLightColor();
    vec3 shadow = vec3(0.0);
#if !defined DIM_NETHER
    if (flatNdotL > -0.02 || sss > 0.0 || foliage) {
        shadow = getShadow(playerPos, foliage ? vec3(0.0) : normalW, noise, 1.0);
    }
#endif
    // beyond the shadow map / in caves: skylight decides
    shadow *= smoothstep(0.0, 0.25, lm.y) * 0.8 + 0.2 * step(0.999, lm.y);
    shadow *= pomShadow;

    float diffuseTerm = foliage ? saturate(flatNdotL * 0.5 + 0.5) * 0.85 : saturate(NdotL);
    vec3 direct = lightCol * shadow * diffuseTerm;

    // ambient
    float sky = lm.y * lm.y;
    float upness = (mat3(gbufferModelViewInverse) * N).y * 0.5 + 0.5;
    vec3 ambient = skyAmbientColor() * sky * (0.7 + 0.3 * upness);
    float block = lm.x;
#ifdef HANDHELD_LIGHT
    float held = float(max(heldBlockLightValue, heldBlockLightValue2)) / 15.0;
    block = max(block, held * saturate(1.0 - length(viewPos) / max(held * 15.0, 0.01)));
#endif
    ambient += blockLightColor(block);
    ambient += vec3(MIN_LIGHT) * (1.0 + nightVision * 6.0);
    ambient *= m.ao;

    vec3 diffuse = m.albedo * (direct + ambient);

    // subsurface scattering (leaves, grass, snow, wool...)
    if (sss > 0.0) {
        float phase = henyeyGreenstein(dot(-V, L), 0.55) * 2.5 + 0.3;
        diffuse += m.albedo * lightCol * shadow * sss * phase * 0.6 * (1.0 - saturate(flatNdotL) * 0.5);
    }

    // specular
    float roughness = sq(1.0 - m.smoothness);
    vec3 spec = vec3(0.0);
    if (m.f0raw > 0.5) {
        spec = specularGGX(N, V, L, roughness, m.f0) * lightCol * shadow;
        // cheap ambient reflection for surfaces that are too rough for SSR
    #ifdef SSR
        if (m.smoothness < SSR_THRESHOLD)
    #endif
        {
            vec3 F = fresnelSchlick(dot(N, V), m.f0);
            vec3 Rw = mat3(gbufferModelViewInverse) * reflect(-V, N);
            spec += F * getSky(Rw) * sky * sq(m.smoothness) * 0.8 * m.ao;
        }
    }
    if (m.metal) diffuse *= 0.12;

    vec3 emission = m.albedo * m.emission * EMISSION_STRENGTH * 2.0;
    return diffuse + spec + emission;
}
