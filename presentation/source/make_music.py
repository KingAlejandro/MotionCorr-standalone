#!/usr/bin/env python3
"""Original instrumental score: deterministic synthesis, no sampled recordings.

A soft 112 BPM electronic cue in D minor, with restrained percussion, warm
pads and short mallet arpeggios. Deliberately mixed below speech level.
"""
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT=Path(__file__).resolve().parents[1]
SR=44100
DURATION=180
BPM=112
BEAT=60/BPM
N=round(DURATION*SR)
audio=np.zeros((N,2),dtype=np.float32)
rng=np.random.default_rng(24092026)

def freq(m):
    return 440*2**((m-69)/12)

def add(x,start,amp=1,pan=0):
    a=round(start*SR)
    if a>=N:return
    if a<0:x=x[-a:];a=0
    z=min(len(x),N-a)
    if z<=0:return
    angle=(np.clip(pan,-1,1)+1)*np.pi/4
    audio[a:a+z,0]+=x[:z]*amp*np.cos(angle)
    audio[a:a+z,1]+=x[:z]*amp*np.sin(angle)

def tone(note,dur,kind='mallet'):
    t=np.arange(round(dur*SR),dtype=np.float32)/SR
    f=freq(note)
    if kind=='mallet':
        x=(np.sin(2*np.pi*f*t)*np.exp(-t/0.48)+.32*np.sin(2*np.pi*f*2*t)*np.exp(-t/.18)
           +.075*np.sin(2*np.pi*f*3*t)*np.exp(-t/.095))
        x*=np.minimum(t/.009,1)
    elif kind=='bass':
        x=(np.sin(2*np.pi*f*t)+.22*np.sin(2*np.pi*f*2*t)+.08*np.sin(2*np.pi*f*3*t))
        x*=np.minimum(t/.018,1)*np.minimum((dur-t)/.09,1)*np.exp(-t/1.1)
    else:
        env=np.minimum(t/.65,1)*np.minimum((dur-t)/1.1,1)
        x=(np.sin(2*np.pi*f*t)+.35*np.sin(2*np.pi*f*1.0016*t+.8)
           +.17*np.sin(2*np.pi*f*2*t+.4))*.66
        x*=np.maximum(env,0)*(.94+.06*np.sin(2*np.pi*.19*t))
    return x.astype(np.float32)

def kick():
    t=np.arange(round(.36*SR),dtype=np.float32)/SR
    phase=2*np.pi*(44*t+52*.035*(1-np.exp(-t/.035)))
    return np.sin(phase)*np.exp(-t/.078)*np.minimum(t/.003,1)

def hat(opened=False):
    dur=.20 if opened else .07
    t=np.arange(round(dur*SR),dtype=np.float32)/SR
    noise=rng.standard_normal(len(t)).astype(np.float32)
    filt=signal.sosfilt(signal.butter(2,7000,btype='highpass',fs=SR,output='sos'),noise)
    return filt*np.exp(-t/(.038 if opened else .013))*np.minimum(t/.002,1)

def rim():
    t=np.arange(round(.13*SR),dtype=np.float32)/SR
    noise=rng.standard_normal(len(t))
    noise=signal.sosfilt(signal.butter(2,[1400,7000],btype='bandpass',fs=SR,output='sos'),noise)
    return (noise*.25+np.sin(2*np.pi*1720*t)*.28+np.sin(2*np.pi*1210*t)*.3)*np.exp(-t/.020)*np.minimum(t/.0015,1)

# Four harmonic colours, each held for four bars.
chords=[[50,57,60,64,69],[46,53,57,60,65],[48,53,57,60,67],[48,55,58,62,67]]
roots=[38,34,41,36]
for bar in range(0,84,4):
    start=bar*4*BEAT
    chord=chords[(bar//4)%4]
    if start>=171:
        chord=[50,57,60,64,69]
    for j,note in enumerate(chord):
        add(tone(note,4*4*BEAT+1.1,'pad'),start-.1,.036,pan=(j-2)*.36)

K=kick();R=rim();H=hat();O=hat(True)
for beat in range(336):
    start=beat*BEAT
    bar=beat//4
    phrase=(bar//4)%4
    active=1.0
    if start<10:active=.0
    elif start<22:active=.55
    elif 100<=start<113:active=.52
    elif 113<=start<114.4:active=0
    elif 124<=start<149:active=.95
    elif 163<=start<175:active=.72
    elif start>=175:active=0
    if beat%4 in [0,2]:
        add(K,start,.23*active)
    if beat%4 in [1,3]:
        add(R,start,.12*active,pan=.11)
    add(H,start,.034*active,pan=-.33)
    add(H,start+BEAT/2,.047*active,pan=.34)
    if beat%8==7:
        add(O,start+BEAT*.5,.022*active,pan=.4)
    if start>=10 and start<175 and beat%4 in [0,2,3]:
        note=roots[phrase]+(12 if beat%8==7 else 0)
        add(tone(note,BEAT*.91,'bass'),start,.095*max(active,.28),pan=-.04)

# A sparse repeating motif, rather than constant frenetic arpeggiation.
pattern=[0,2,3,1,4,3,2,1]
for bar in range(84):
    start=bar*4*BEAT
    if start<7 or start>174:continue
    chord=chords[(bar//4)%4]
    positions=[0,1.5,2.5] if bar%2==0 else [1,3.0]
    if 100<start<124:positions=[.5,2.5]
    for k,b in enumerate(positions):
        note=chord[pattern[(bar*3+k)%len(pattern)]]+12
        if note>84:note-=12
        x=tone(note,1.3)
        amp=.052 if start<124 else .062
        pan=np.sin(bar*.7+k)*.55
        add(x,start+b*BEAT,amp,pan)
        add(x,start+b*BEAT+BEAT*.75,amp*.19,-pan)
        add(x,start+b*BEAT+BEAT*1.5,amp*.08,pan*.6)

# Quiet opening and closing motifs; no synthetic voice.
for t,n in [(0.3,74),(0.58,81),(1.08,77),(5.05,74),(5.34,77),(5.64,81),
            (175.15,74),(175.42,77),(175.75,81),(176.2,86)]:
    add(tone(n,2.6),t,.070,pan=np.sin(t)*.25)

# Very gentle, short scene-change sweeps, generated from noise.
for start in [33.75,59.75,87.75,123.75,162.75,174.75]:
    t=np.arange(round(.44*SR),dtype=np.float32)/SR
    n=rng.standard_normal(len(t)).astype(np.float32)
    n=signal.sosfilt(signal.butter(2,[800,4200],btype='bandpass',fs=SR,output='sos'),n)
    env=np.sin(np.pi*np.arange(len(t))/len(t))**2
    add((n*env).astype(np.float32),start,.025,pan=-.1)

# Light stereo ambience, using quiet delayed copies rather than sampled reverb.
for delay,gain in [(0.083,.075),(.147,.055),(.229,.04),(.367,.03)]:
    d=round(delay*SR)
    audio[d:,0]+=audio[:-d,1]*gain
    audio[d:,1]+=audio[:-d,0]*gain
# No DC, controlled transients and a spacious, narration-friendly mix.
audio=signal.sosfilt(signal.butter(2,28,btype='highpass',fs=SR,output='sos'),audio,axis=0).astype(np.float32)
audio=np.tanh(audio*1.2)/1.2
peak=float(np.max(np.abs(audio)))
audio*=.53/max(peak,1e-8)
fade_in=np.minimum(np.arange(N,dtype=np.float32)/(SR*.9),1)
fade_out=np.minimum((N-1-np.arange(N,dtype=np.float32))/(SR*3.0),1)
audio*=np.maximum(0,fade_in*fade_out)[:,None]
path=ROOT/'assets/original-score.wav'
wavfile.write(path,SR,np.int16(np.clip(audio,-1,1)*32767))
print({'path':str(path),'duration':DURATION,'peak_dbfs':20*np.log10(np.max(np.abs(audio))),
       'rms_dbfs':20*np.log10(np.sqrt(np.mean(audio**2)))})
