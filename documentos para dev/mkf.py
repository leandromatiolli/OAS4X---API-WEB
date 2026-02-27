import numpy as np
import time
import sys
#import cupy as np
#


invspace = lambda start,stop,n_steps:1/np.linspace(1/start,1/stop, n_steps)
movavg = lambda x, w, mode='same': np.convolve(x, np.ones(w), mode) / w

def dbexpulse(t, t_up, t_down):
    '''
    Double exponential pulse. Pulse with exponential raise and exponential decay.
    
    t_up: raise time
    t_down: decay time
    '''
    signal = (np.exp(-t/t_down)-np.exp(-t/t_up))*np.heaviside(t,0)
    return signal

def expulse(t,f, t_up, t_down, phase=0, real=True):
    '''
    Modulated Double exponential pulse. Pulse with exponential raise and exponential decay. 
    
    f: carrier frequency
    phase: phase of the carrier
    t_up: raise time
    t_down: decay time
    real: return real signal if True else return Complex
    '''
    carrier = np.sin(phase+2*np.pi*f*t) if real else np.exp(1j*(phase+2*np.pi*f*t))
    return dbexpulse(t, t_up ,t_down)*carrier
    
expulse2 = lambda t, f, phase=0: expulse(t, f, 1/f, 30/f, phase) 

dB = lambda x:10*np.log10(x)

def decimate(signal, factor):
    return signal[np.arange(0,signal.shape[-1], factor)]

def transform(data, alpha = 2*np.pi/3, center=np.array([[0,0]]).T, amps=np.array([[1,1]]).T):  
    if type(data) is list and type(data[0]) is np.ndarray:
        np.vstack(data)
    out = np.empty_like(data, dtype=np.float32)
    temp = np.empty_like(data[0], dtype=np.float32)
    np.subtract(data, center, out=out)
    np.multiply(out, 2/amps, out =out)
    np.multiply(out[0], np.cos(alpha), out = temp)
    np.subtract(temp, out[1], out = temp)
    np.multiply(temp, 1/np.sin(alpha), out = temp)
    out = out[0] + 1j*temp
    return out
    
def get_iq2(V, a , b):
    "Get IQ with correction of angle"
    print('test2')
    delta = a+b
    phi   = a-b
    adds = np.sin(phi) + np.sin(delta)
    subs = np.sin(phi) - np.sin(delta)
    subc = np.cos(phi) - np.cos(delta)
    addc = np.cos(phi) + np.cos(delta)
    sqrt3 = np.sqrt(3)
    part = V[1]-V[2] - 0.5*V[0]*(subc-sqrt3*adds)
    i = (2*V[0] - V[1]- V[2] )/3
    return V[0] +2j*part/(addc*sqrt3+subs)

def get_iq(X,ch=[0,1,2]):
    i = (2*X[ch[0]]-X[ch[1]]-X[ch[2]])/3
    q = (X[ch[1]]-X[ch[2]])/np.sqrt(3)
    return i + 1j*q
    
def demodulate(waveforms, param = None):
    demo = lambda x, param: np.unwrap(np.arctan2(*rescale(*x, param)))
    shape = waveforms.shape
    if len(shape) == 2:
        if param is None:
            raise Exception("Needs ellipse_param")
        if shape[0] == 2:
            return demo(waveforms, param)
        elif shape[1] == 2:
            return demo(waveforms.T, param)
        else:
            raise Exception("One of the dimension needs to be 2")
    if len(shape) == 3:
        demodulated = np.empty((shape[0], shape[2]))
        for i in range(shape[0]):
            print(f"Demodulating={i+1:04d}/{shape[0]}", end='\r')
            demodulated[i] =  demo(waveforms[i], param)
        return demodulated

def fft(signal, fs=None, t=None, dB=True, window=True, window_type='hamming'):
    N = signal.shape[0]
    if window:
        from scipy.signal import get_window
        signal= signal*get_window(window_type, N)
    ft = np.fft.fft(signal)*(2/N)
    ft = ft[0:N//2]
    ft = np.abs(ft)
    ft = 10*np.log10(ft) if dB else ft
    if t is not None:
        fs = 1/(t[1]-t[0])
    if fs is not None:
        f = np.arange(0,N//2)*fs/N
        return f, ft
    return ft


#gaussian = lambda wv, delta_wv: np.exp(-np.pi*((wv-1.55)/delta_wv)**2)/delta_wv*(wv[0]-wv[1])
def gaussian_e(x, delta_x):
    '''
    Energy (or area under the gaussian) conserved.
    exp(-2pi(x/delta_x)^2)/delta_x*(x[0]-x[1])
    '''
    return np.exp(-np.pi*(x/delta_x)**2)/delta_x*np.abs(x[1]-x[0])
def gaussian_n(x, delta_x):
    '''
    Gaussian with peak value 1.
    exp(-2pi(x/delta_x)^2)
    '''
    return np.exp(-np.pi*(x/delta_x)**2)

class FT:
    def __init__(self, signal, dt=None, t=None, fs=None):
        self.N = N = len(signal)
        self.no_t = False
        self.signal = signal
        if t is not None:
            self.dt = t[1] - t[0]  
            self.t = t
            self.fs = fs = 1/self.dt
        elif dt is not None:
            self.dt = dt
            self.t = np.arange(0,N)*self.dt
            self.fs = fs = 1/self.dt
        elif fs is not None:
            self.fs = fs
            self.dt = 1/fs
            self.t = np.arange(0,N)*self.dt
        else:
            self.no_t = True
            return                
        self.f = np.arange(-N/2,N/2)*fs/N
        self.f2 = np.arange(0,N//2)*fs/N
        self.ft = 2*np.fft.fft(self.signal)/self.N
    
    def abs(self, dB=False, freq='half'):
        if freq == 'half':
            f = self.f2
            ft = self.ft[:self.N//2]
        else:
            f = self.f
            ft = self.ft
        ft = np.abs(ft)
        if dB:
            ft = 10*np.log10(ft)
        return f, ft
    
    def ftas(self, dB=False):
        y = np.fft.fftshift(np.abs(2*np.fft.fft(self.signal)))/self.N
        if dB:
            return self.f, 10*np.log10(y)
        else:
            return self.f, y

    def ift(self):
        return self.f, np.fft.ifft(self.signal)*self.N/2
    
    def deriv(self):
        fhat = np.fft.fft(self.signal)
        L = (self.t[-1]-self.t[0])
        kappa = np.arange(-self.N//2,self.N//2)*2*np.pi/L
        kappa = np.fft.fftshift(kappa) 
        dfhat = kappa*fhat*(1j)
        return np.fft.ifft(dfhat)
    
    def integral(self):
        fhat = np.fft.fft(self.signal)
        L = (self.t[-1]-self.t[0])
        kappa = np.arange(-self.N//2,self.N//2)*L/(2*np.pi)
        kappa = np.fft.fftshift(kappa) 
        dfhat = -kappa*fhat*(1j)
        return np.fft.ifft(dfhat)
    
    def plot(self, dB=False):
        import matplotlib.pyplot as plt
        plt.plot(*self.ftas(dB))
        
def read_wav_files(filename, n_channels=2, dtype=np.int16):
    import wave
    with wave.open(filename) as wf:
        frames = wf.readframes(wf.getnframes())
    return np.frombuffer(frames, dtype=dtype).reshape([length,n_channels]).T


def EDFA(wv):
    
    p = np.array([ 1.54302776e+00,  1.55655997e+00, 1.53085119e+00,  
                   6.66346301e+04,  8.93820024e+04, 2.87144911e+05, 
                  -9.59250258e-01, -2.45997820e+00, 7.17825207e+00])
    f1 = lambda wv,wv0,dwv:(- (wv-wv0)*(wv-wv0))*dwv
    x1,x2,x3, d1,d2,d3, p1,p2,p3 = p
    #f = lambda wv,x1,x2,x3, d1,d2,d3, p1,p2,p3: 10**((f1(wv, x1,d1)+p1)/10)+10**((f1(wv, x2,d2)+p2)/10)+10**((f1(wv, x3,d3)+p3)/10)
    #plt.plot(wv,np.log(f(wv, *p)))
    out = 10**((f1(wv, x1,d1)+p1)/10)+10**((f1(wv, x2,d2)+p2)/10)+10**((f1(wv, x3,d3)+p3)/10)
    out2 = out/np.sum(out)
    return  out2

def nSi(wl):
    B1 = 10.6684293
    B2 = 0.0030434748
    B3 = 1.54133408
    C1 = 0.0909121907
    C2 = 1.28766018
    C3 = 1218816 
    coeff = [
        (B1, C1),
        (B2, C2),
        (B3, C3),
    ]
    wl2 = wl*2
    n2 = 1 + sum(Bi*wl2/(wl2-Ci) for Bi,Ci in coeff)
    return np.sqrt(n2)

def nSiO2(wl):
    B1 = 0.6961663
    B2 = 0.4079426
    B3 = 0.8974794
    C1 = 0.0684043**2
    C2 = 0.1162414**2
    C3 = 9.896161**2
    coeff = [
        (B1, C1),
        (B2, C2),
        (B3, C3),
    ]
    wl2 = wl*2
    n2 = 1 + sum(Bi*wl2/(wl2-Ci) for Bi,Ci in coeff)
    return np.sqrt(n2)

def neff_450wg(wv):
    neff_table =(
        (1.50, 2.3428),
        (1.51, 2.3297),
        (1.52, 2.3165),
        (1.53, 2.3034),
        (1.54, 2.2902),
        (1.55, 2.2770),
        (1.56, 2.2639),
        (1.57, 2.2507),
        (1.58, 2.2375),
        (1.59, 2.2244),
        (1.60, 2.2113),
    )
    coef = np.polyfit(*zip(*neff_table),2)
    return np.poly1d(coef)(wv)



def get_ng(n):
    def ng(wv):
        delta = 0.0001
        return n(wv) + wv*(n(wv+delta/2)-n(wv-delta/2))/delta
    return ng
   
class MI_PLM:
    def __init__(self, n1, n2, spectrum, wv):
        try:
            self.p1 = lambda L:2*np.pi*float(n1)*L/wv
        except:
            self.p1 = lambda L:2*np.pi*n1(wv)*L/wv
        try:
            self.p2 = lambda L:2*np.pi*float(n2)*L/wv
        except:
            self.p2 = lambda L:2*np.pi*n2(wv)*L/wv
        self.dp = lambda L, dL:self.p1(L) - self.p2(dL)
        self.I = lambda L, dL: spectrum(wv)*(1+np.cos(self.dp(L, dL)))/2                            
        self.P = lambda L,dL: np.sum(self.I(L,dL),axis=0)
        
def read_rigol_file(filename):
    import RigolWFM.wfm as wfm
    obj = wfm.Wfm.from_file(filename, model = 'DS1054Z')
    wfm.Wfm.get_numpy_raw = lambda self:np.vstack([ch.raw for ch in self.channels])
    wfm.Wfm.get_numpy_volts = lambda self:np.vstack([ch.volts for ch in self.channels])
    wfm.Wfm.times = lambda self:self.channels[0].times
    return obj

class dotdict(dict):
    """
    dot.notation access to dictionary attributes
    https://stackoverflow.com/questions/2352181/how-to-use-a-dot-to-access-members-of-dictionary
    """
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__
    def __dir__(self):     return dir(dict) + list(self.keys())
    def __getstate__(self): return self.__dict__
    def __setstate__(self, d): self.__dict__.update(d)
    def __getattr__(self, key):
        try:
            return self.__getitem__(key)
        except KeyError:
            # or other errors that may occur
            raise AttributeError(key)
            
pack = lambda variables_list, globals:dotdict({name : globals[name] for name in variables_list})

def arr_from_ptr(pointer, typestr, shape, copy=False,
                 read_only_flag=False):
    """Generates numpy array from memory address
    https://docs.scipy.org/doc/numpy-1.13.0/reference/arrays.interface.html

    Parameters
    ----------
    pointer : int
        Memory address

    typestr : str
        A string providing the basic type of the homogenous array The
        basic string format consists of 3 parts: a character
        describing the byteorder of the data (<: little-endian, >:
        big-endian, |: not-relevant), a character code giving the
        basic type of the array, and an integer providing the number
        of bytes the type uses.

        The basic type character codes are:

        - t Bit field (following integer gives the number of bits in the bit field).
        - b Boolean (integer type where all values are only True or False)
        - i Integer
        - u Unsigned integer
        - f Floating point
        - c Complex floating point
        - m Timedelta
        - M Datetime
        - O Object (i.e. the memory contains a pointer to PyObject)
        - S String (fixed-length sequence of char)
        - U Unicode (fixed-length sequence of Py_UNICODE)
        - V Other (void * – each item is a fixed-size chunk of memory)

        See https://docs.scipy.org/doc/numpy-1.13.0/reference/arrays.interface.html#__array_interface__

    shape : tuple
        Shape of array.

    copy : bool
        Copy array.  Default False

    read_only_flag : bool
        Read only array.  Default False.
    """
    buff = {'data': (pointer, read_only_flag),
            'typestr': typestr,
            'shape': shape}

    class numpy_holder():
        pass

    holder = numpy_holder()
    holder.__array_interface__ = buff
    return np.array(holder, copy=copy)

def fit_ellipse(R, G):
    x2 = np.float32(R)
    y2 = np.float32(G)
    A2 = np.vstack([x2**2, y2**2, x2*y2, x2, y2]).T
    A, B, C, D, E = np.linalg.lstsq(A2, np.ones_like(x2), rcond=None)[0]
    alpha = -np.arcsin(C/np.sqrt(4*A*B))
    r = np.sqrt(B/A)
    p = (2*B*D-E*C)/(C**2-4*A*B)
    q = (2*A*E-D*C)/(C**2-4*A*B)
    s = np.sqrt(p**2 + (1/A + (q**2)*(r**2) + 2*p*q*r*np.sin(alpha) + (p**2)*np.sin(alpha)**2)/np.cos(alpha)**2)
    return p, q, r, s, alpha

#def rescale(R, G, param, invert=False):
#    R = np.float32(R)
#    G = np.float32(G)
#    x2, y2 = R, G
#    p, q, r, s, alpha = param
#    x = x2 - p
#    y = ((y2 - q)*r + x*np.sin(alpha))/np.cos(alpha)
#    return x/s, y/s

def rescale(R, G, param, invert=False):
    '''
    alpha: angulo da 3x3
    r: excentricidade da elipse
    s: tamanho da elipse
    p: nivel medio de x
    q: nivel medio de y
    '''
    x2 = np.float32(R)
    y2 = np.float32(G)

    p, q, r, s, alpha = param
    if invert:
        x = s*x2 + p 
        y = s*(y2*np.cos(alpha) - x2*np.sin(alpha))/r + q
    else:
        x = (x2 - p)/s
        y = ((y2 - q)*r + (x2 - p)*np.sin(alpha))/np.cos(alpha)/s
    return x, y

def arg_closest_to(value, array):
    return np.argmin(np.abs(array - value))
                     
def sinfunc(p):
    return lambda t: p["amp"] * np.sin((2.*np.pi*p["freq"])*t + p["phase"]) + p["offset"] + p["slope"]*t

def fit_sin(tt, yy, freq):
    from scipy.optimize import curve_fit
    '''Fit sin to the input time sequence, and return fitting parameters "amp", "omega", "phase", "offset", "freq", "period" and "fitfunc"'''
    tt = np.array(tt)
    yy = np.array(yy)
    guess_amp = np.std(yy) * 2.**0.5
    guess_offset = np.mean(yy)
    guess_slope = 0.0
    guess_phase = 0.0
    guess = np.array([guess_amp, guess_phase, guess_offset, guess_slope])  
    sinfunc = lambda t, A, p, c, s:  A * np.sin((2.*np.pi*freq)*t + p) + c + s*t
    popt, pcov = curve_fit(sinfunc, tt, yy, p0=guess)
    return {"amp": popt[0], "phase": popt[1], "offset": popt[2], "freq": freq, "slope": popt[3]}


def measure_spectrum(setup, freqs, meta_out=sys.stdout, data_out=sys.stdout, plot=None):
    meta_out.write(f'timestamp_start:{time.time()}\n')
    dig, sg = setup
    R,G = dig.acquire_calibration()
    param = fit_ellipse(R, G)
    labels = ["amp", "phase", "offset", "freq", "slope", "fit_std", "rescale_std"]
    data_points = np.zeros_like((len(freqs), len(labels)))
    #samples = np.zeros((len(freqs)),dtype=np.float32)
    meta_out.write(f'ellipse_param:{param}\n')
    dig.set_acquire()
    t = dig.time_axis()  
    sg.set_frequency(freqs[0])
    data_out.write(" ".join(labels)+'\n')
    if plot is not None and not plot[1][0].lines:
        fig, ax, QApplication = plot
        ax[0].plot(t,np.zeros_like(t), color='b')
        ax[0].plot(t,np.zeros_like(t), color='r')
    for i, gen_frequency in enumerate(freqs):
        t1 = time.time()
        time.sleep(1)
        R, G = dig.acquire()
        sg.set_frequency(freqs[(i+1)%len(freqs)])
        #meta_out.write(f'timestamp_aquired:{time.time()}\n')
        demodulated = demodulate(R, G, param)
        p = fit_sin(t, demodulated, gen_frequency)     
        if plot is not None:
            fig, ax, QApplication = plot
            ax[0].lines[0].set_ydata(demodulated)
            ax[0].lines[1].set_ydata(sinfunc(p)(t))
            ax[0].set_ylim([min(demodulated),max(demodulated)])
            ax[0].set_xlim(min(t),max(t))
            fig.canvas.draw()
            QApplication.processEvents()
        p["fit_std"] = np.std(demodulated - sinfunc(p)(t))
        p['samples'] = sample([R, G], demodulated)
        x,y = rescale(p['samples'][0], p['samples'][1], param)
        p['rescale_std'] = np.std(np.sqrt(x**2+y**2))
        #data_points[i] = np.array([p[label] for label in labels])
        data_out.write(" ".join([f"{p[label]:.4e}" for label in labels])+'\n')
        #meta_out.write(f'timestamp_step:{time.time()}\n')
    #data = dict()
    #data['timestamp_start'] = t0
    #data['timestamp_stop'] = time.time()
    #data['ellipse_param'] = param
    #data['data_points'] = data_points
    return

def sample(data, angles, n_points = 10):
   # samples = np.zeros((2, n_points),dtype=np.uint8)
    MAX = max(angles)
    MIN = min(angles)
    intermediate = np.linspace(MIN, MAX, n_points)
    samples = []
    for i in range(n_points):
        j = arg_closest_to(intermediate[i], angles)
        samples += [data[0][j], data[1][j]]
        #samples[0][i] = data[0][j]
        #samples[1][i] = data[1][j]
    return list(zip(*samples))

def q15_to_float(x):
    y = x.astype(np.float32)/(1 << 15)
    if(dtype == np.uint16):
        y -= (x>>15)*2
    return y