#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project: Diff-expert
@Name: preprocess.py
"""
from tqdm import tqdm
import copy
import time
import pickle as pk
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
import os
from scipy import interpolate
import scipy.ndimage as ndimage
from math import radians, cos, sin, asin, sqrt
from pyproj import Geod
geod = Geod(ellps='WGS84')
#import dataset

AVG_EARTH_RADIUS = 6378.137  # in km
SPEED_MAX = 30 # knot
FIG_DPI = 150
LAT,LON,SOG,COG,HEAD, NAV,TIMESTAMP,MMSI = range(8)


def trackOutlier(A):
    """
    Koyak algorithm to perform outlier identification
    Our approach to outlier detection is to begin by evaluating the expression
    “observation r is anomalous with respect to observation s ” with respect to
    every pair of measurements in a track. We address anomaly criteria below; 
    assume for now that a criterion has been adopted and that the anomaly 
    relationship is symmetric. More precisely, let a(r,s) = 1 if r and s are
    anomalous and a(r,s) = 0 otherwise; symmetry implies that a(r,s) = a(s,r). 
    If a(r,s) = 1 either one or both of observations are potential outliers, 
    but which of the two should be treated as such cannot be resolved using 
    this information alone.
    Let A denote the matrix of anomaly indicators a(r, s) and let b denote 
    the vector of its row sums. Suppose that observation r is an outlier and 
    that is the only one present in the track. Because we expect it to be 
    anomalous with respect to many if not all of the other observations b(r) 
    should be large, while b(s) = 1 for all s ≠ r . Similarly, if there are 
    multiple outliers the values of b(r) should be large for those observations
    and small for the non-outliers. 
    Source: "Predicting vessel trajectories from AIS data using R", Brian L 
    Young, 2017
    INPUT:
        A       : (nxn) symmatic matrix of anomaly indicators
    OUTPUT:
        o       : n-vector outlier indicators
    
    # FOR TEST
    A = np.zeros((5,5))
    idx = np.array([[0,2],[1,2],[1,3],[0,3],[2,4],[3,4]])
    A[idx[:,0], idx[:,1]] = 1
    A[idx[:,1], idx[:,0]] = 1    sampling_track = np.empty((0, 9))
    for t in range(int(v[0,TIMESTAMP]), int(v[-1,TIMESTAMP]), 300): # 5 min
        tmp = utils.interpolate(t,v)
        if tmp is not None:
            sampling_track = np.vstack([sampling_track, tmp])
        else:
            sampling_track = None
            break
    """
    assert (A.transpose() == A).all(), "A must be a symatric matrix"
    assert ((A==0) | (A==1)).all(), "A must be a binary matrix"
    # Initialization
    n = A.shape[0]
    b = np.sum(A, axis = 1)
    o = np.zeros(n)
    while(np.max(b) > 0):
        r = np.argmax(b)
        o[r] = 1
        b[r] = 0
        for j in range(n):
            if (o[j] == 0):
                b[j] -= A[r,j]
    return o.astype(bool)
    
#===============================================================================
#===============================================================================
def detectOutlier(track, speed_max = SPEED_MAX):
    """
    removeOutlier() removes anomalus AIS messages from AIS track.
    An AIS message is considered as beging anomalous if the speed is
    infeasible (> speed_max). There are two types of anomalous messages:
        - The reported speed is infeasible
        - The calculated speed (distance/time) is infeasible
    
    INPUT:
        track       : a (nxd) matrix. Each row is an AIS message. The structure 
                      must follow: [Timestamp, Lat, Lon, Speed]
        speed_max   : knot
    OUTPUT:
        o           : n-vector outlier indicators
    """
    # Remove anomalous reported speed
    o_report = track[:,3] > speed_max # Speed in track is in knot
    if o_report.all():
        return o_report, None
    track = track[np.invert(o_report)]
    # Calculate speed base on (lon, lat) and time
    
    N = track.shape[0]
    # Anomoly indicator matrix
    A = np.zeros(shape = (N,N))
    
    # Anomalous calculated-speed
    for i in range(1,5):
        # the ith diagonal
        _, _, d = geod.inv(track[:N-i,2],track[:N-i,1],
                           track[i:,2],track[i:,1])
        delta_t = track[i:,0] - track[:N-i,0].astype(np.float)  
        cond = np.logical_and(delta_t > 2,d/delta_t > (speed_max*0.514444))
        abnormal_idx = np.nonzero(cond)[0]
        A[abnormal_idx, abnormal_idx + i] = 1
        A[abnormal_idx + i, abnormal_idx] = 1    

    o_calcul = trackOutlier(A)
            
    return o_report, o_calcul
    
#===============================================================================
#===============================================================================
def interpolate_(t, track):
    """
    Interpolating the AIS message of vessel at a specific "t".
    INPUT:
        - t : 
        - track     : AIS track, whose structure is
                     [LAT, LON, SOG, COG, HEADING, ROT, NAV_STT, TIMESTAMP, MMSI]
    OUTPUT:
        - [LAT, LON, SOG, COG, HEADING, ROT, NAV_STT, TIMESTAMP, MMSI]
                        
    """
    
    before_p = np.nonzero(t >= track[:,TIMESTAMP])[0]
    after_p = np.nonzero(t < track[:,TIMESTAMP])[0]
   
    if (len(before_p) > 0) and (len(after_p) > 0):
        apos = after_p[0]
        bpos = before_p[-1]    
        # Interpolation
        dt_full = float(track[apos,TIMESTAMP] - track[bpos,TIMESTAMP])
        if (abs(dt_full) > 2*3600):
            return None
        dt_interp = float(t - track[bpos,TIMESTAMP])
        try:
            az, _, dist = geod.inv(track[bpos,LON],
                                   track[bpos,LAT],
                                   track[apos,LON],
                                   track[apos,LAT])
            dist_interp = dist*(dt_interp/dt_full)
            lon_interp, lat_interp, _ = geod.fwd(track[bpos,LON], track[bpos,LAT],
                                               az, dist_interp)
            speed_interp = (track[apos,SOG] - track[bpos,SOG])*(dt_interp/dt_full) + track[bpos,SOG]
            course_interp = (track[apos,COG] - track[bpos,COG] )*(dt_interp/dt_full) + track[bpos,COG]
            heading_interp = (track[apos,HEADING] - track[bpos,HEADING])*(dt_interp/dt_full) + track[bpos,HEADING]  
            rot_interp = (track[apos,ROT] - track[bpos,ROT])*(dt_interp/dt_full) + track[bpos,ROT]
            if dt_interp > (dt_full/2):
                nav_interp = track[apos,NAV_STT]
            else:
                nav_interp = track[bpos,NAV_STT]                             
        except:
            return None
        #LAT, LON, SOG, COG, HEADING, ROT, TIMESTAMP, MMSI, NAV_STT
        return np.array([lat_interp, lon_interp,
                         speed_interp, course_interp, 
                         heading_interp, rot_interp, 
                         t,track[0,MMSI],nav_interp])
    else:
        return None

#======================================
count = 0
voyages = dict()
INTERVAL_MAX = 2*3600 # 2h

for mmsi in list(traj_data.keys()):
    v = traj_data[mmsi]["traj"]
    if v.shape[0]>0:
        # Intervals between successive messages in a track
        intervals = v[1:,TIMESTAMP] - v[:-1,TIMESTAMP]
        idx = np.where(intervals > INTERVAL_MAX)[0]
        if len(idx) == 0:
            voyages[count] = v
            count += 1
        else:
            tmp = np.split(v,idx+1)
            for t in tmp:
                voyages[count] = t
                count += 1
#======================================
print("Removing AIS track whose length is smaller than 75 or those last less than 6h...")

for k in list(voyages.keys()):
    duration = voyages[k][-1,TIMESTAMP] - voyages[k][0,TIMESTAMP]
    if (len(voyages[k]) < 75) or (duration < 6*3600):
        voyages.pop(k, None)

#======================================
print("Removing anomalous message...")
error_count = 0
for k in  tqdm(list(voyages.keys())):
    track = voyages[k][:,[TIMESTAMP,LAT,LON,SOG]] # [Timestamp, Lat, Lon, Speed]
    try:
        o_report, o_calcul = detectOutlier(track, speed_max = 30)
        if o_report.all() or o_calcul.all():
            voyages.pop(k, None)
        else:
            voyages[k] = voyages[k][np.invert(o_report)]
            voyages[k] = voyages[k][np.invert(o_calcul)]
    except:
        voyages.pop(k,None)
        error_count += 1
#======================================
# Sampling, resolution = 5 min
print('Sampling...')
Vs = dict()
count = 0
resolution = 5*60
for k in tqdm(list(voyages.keys())):
    v = voyages[k]
    sampling_track = np.empty((0, 8))
    for t in range(int(v[0,TIMESTAMP]), int(v[-1,TIMESTAMP]), resolution): # 5 min
        tmp = interpolate_(t,v)
        if tmp is not None:
            sampling_track = np.vstack([sampling_track, tmp])
        else:
            sampling_track = None
            break
    if sampling_track is not None:
        Vs[count] = sampling_track
        count += 1
#======================================
print('Re-Splitting...')
DURATION_MAX = 12#h
one_hour = 12
Data = dict()
count = 0
for k in tqdm(list(Vs.keys())): 
    v = Vs[k]
    # Split AIS track into small tracks whose duration <= 1 day
    idx = np.arange(0, len(v), one_hour*DURATION_MAX)[1:]
    tmp = np.split(v,idx)
    for subtrack in tmp:
        # only use tracks whose duration >= 4 hours
        if len(subtrack) >= one_hour*DURATION_MAX:
            Data[count] = subtrack
            count += 1
#======================================
print("Removing 'moored' or 'at anchor' voyages...")
for k in  tqdm(list(Data.keys())):
    d_L = float(len(Data[k]))

    if np.count_nonzero(Data[k][:,NAV] == 7)/d_L > 0.7 \
    or np.count_nonzero(Data[k][:,NAV] == 8)/d_L > 0.7:
        Data.pop(k,None)
        continue
    sog_max = np.max(Data[k][:,SOG])
    if sog_max < 1.0:
        Data.pop(k,None)
#======================================
print("Removing 'low speed' tracks...")
for k in tqdm(list(Data.keys())):
    d_L = float(len(Data[k]))
    if np.count_nonzero(Data[k][:,SOG] < 2)/d_L > 0.8:
        Data.pop(k,None)


