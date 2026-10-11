// gbuffers_skybasic / gbuffers_skytextured / gbuffers_clouds.
// The sky itself is drawn in deferred; here we only keep vanilla stars and the moon.
#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/util.glsl"

#ifdef VERTEX
out vec2 texcoord;
out vec4 glcolor;
void main() {
    texcoord = (gl_TextureMatrix[0] * gl_MultiTexCoord0).xy;
    glcolor = gl_Color;
    gl_Position = ftransform();
}
#endif

#ifdef FRAGMENT
in vec2 texcoord;
in vec4 glcolor;
layout(location = 0) out vec4 outColor;

void main() {
#if defined SKY_BASIC
    if (renderStage != MC_RENDER_STAGE_STARS) discard;
    #ifndef STARS
        discard;
    #endif
    outColor = vec4(toLinear(glcolor.rgb) * 4.0, glcolor.a);
#elif defined SKY_TEXTURED
    if (renderStage != MC_RENDER_STAGE_MOON) discard;
    vec4 c = texture(gtexture, texcoord) * glcolor;
    outColor = vec4(toLinear(c.rgb) * 3.0, c.a);
#else
    discard;
#endif
}
#endif
