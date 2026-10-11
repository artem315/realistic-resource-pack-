// Bloom, exposure, tonemapping and colour grading.
#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/util.glsl"
#include "/lib/sky.glsl"

const bool colortex0MipmapEnabled = true;

#ifdef VERTEX
out vec2 texcoord;
void main() {
    texcoord = gl_MultiTexCoord0.xy;
    gl_Position = ftransform();
}
#endif

#ifdef FRAGMENT
in vec2 texcoord;
layout(location = 0) out vec4 outColor;

vec3 acesFitted(vec3 x) {
    const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void main() {
    vec3 col = texture(colortex0, texcoord).rgb;

#ifdef BLOOM
    vec3 bloom = vec3(0.0);
    float wsum = 0.0;
    for (int i = 2; i <= 7; i++) {
        float w = 1.0 / float(i);
        bloom += textureLod(colortex0, texcoord, float(i)).rgb * w;
        wsum += w;
    }
    bloom /= wsum;
    col = mix(col, bloom, BLOOM_STRENGTH) + max(bloom - 1.0, 0.0) * BLOOM_STRENGTH;
#endif

    // exposure: brighter in caves and at night
    float skyEye = eyeBrightnessSmooth.y / 240.0;
#if defined DIM_NETHER
    float exposure = 1.4;
#elif defined DIM_END
    float exposure = 1.6;
#else
    float exposure = mix(2.6, mix(2.0, 1.0, dayFactor()), skyEye);
#endif
#ifdef AUTO_EXPOSURE
    float avg = luma(textureLod(colortex0, vec2(0.5), 9.0).rgb);
    exposure *= clamp(pow(0.25 / max(avg * exposure, 1e-4), 0.25), 0.7, 1.5);
#endif
    col *= exposure * EXPOSURE;

    col = acesFitted(col);
    // grading in display space
    col = toSRGB(col);
    col = (col - 0.5) * CONTRAST + 0.5;
    float l = luma(col);
    col = mix(vec3(l), col, SATURATION);
    vec2 c = texcoord - 0.5;
    col *= 1.0 - VIGNETTE * dot(c, c) * 2.2;
    col += (hash12(gl_FragCoord.xy) - 0.5) / 255.0;   // dithering against banding
    outColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
#endif
