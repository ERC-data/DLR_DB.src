# -*- coding: utf-8 -*-
"""

@author: Wiebke Toussaint

This file contains functions to fetch data from the Domestic Load Research SQL Server database. It must be run from a server with a DLR database installation.

The following functions are defined:
    getData 
    getProfileID
    getMetaProfiles
    profileFetchEst
    getProfiles
    getSampleProfiles
    profilePeriod
    getGroups
    getLocation
    saveTables
    saveAllProfiles
    anonAns
    
SOME EXAMPLES 

# Using getData with SQL queries:

query = 'SELECT * FROM [General_LR4].[dbo].[linktable] WHERE ProfileID = 12005320'
df = getData(querystring = query)
    
"""

import pandas as pd
import numpy as np
import pyodbc 
from datetime import datetime
from sqlalchemy import create_engine 
import feather
import os

dir_path = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.abspath(os.path.join(dir_path, os.pardir))

with open('cnxnstr.txt', 'r') as f: 
    cnxnstr = f.read().replace('\n', '')
engine = create_engine("mssql+pyodbc:///?odbc_connect=%s" % cnxnstr)

def getData(tablename = None, querystring = 'SELECT * FROM tablename', chunksize = 10000):
    """
    Fetches a specified table from the DLR database and returns it as a pandas dataframe.

    """
    #connection object:
    with open('cnxnstr.txt', 'r') as f: 
        cnxnstr = f.read().replace('\n', '')
    cnxn = pyodbc.connect(cnxnstr)
    
    #specify and execute query(ies):
    if querystring == "SELECT * FROM tablename":
        if tablename is None:
            return print('Specify a valid table from the DLR database')
        elif tablename == 'Profiletable':
            return print('The profiles table is too large to read into python in one go. Use the getProfiles() function.') 
        else:
            query = "SELECT * FROM [General_LR4].[dbo].%s" % (tablename)
    else:
        query = querystring
        
    df = pd.read_sql(query, cnxn)   #read to dataframe   
    return df

def getProfileID(year = None):
    """
    Fetches all profile IDs for a given year. None returns all profile IDs.
    
    """
    links = getData('LinkTable')
    allprofiles = links[(links.GroupID != 0) & (links.ProfileID != 0)]
    if year is None:
        return allprofiles
    #match GroupIDs to getGroups to get the profile years:
    else:
        profileid = pd.Series(allprofiles.loc[allprofiles.GroupID.isin(getGroups(year).GroupID), 'ProfileID'].unique())
    return profileid

def getAnswerID():
    """
    Fetches all answer IDs for a given year. None returns all answer IDs.
    
    """
    links = getData('LinkTable')
    allanswers = links[(links.GroupID != 0) & (links.AnswerID != 0)]
    return allanswers

def getMetaProfiles(year, units = None):
    """
    Fetches profile meta data. Units must be one of  V, A, kVA, Hz or kW.
    
    """
    #list of profiles for the year:
    pids = pd.Series(map(str, getProfileID(year))) 
    #get observation metadata from the profiles table:
    metaprofiles = getData('profiles')[['Active','ProfileId','RecorderID','Unit of measurement']]
    metaprofiles = metaprofiles[metaprofiles.ProfileId.isin(pids)] #select subset of metaprofiles corresponding to query
    metaprofiles.rename(columns={'Unit of measurement':'UoM'}, inplace=True)
    metaprofiles.loc[:,['UoM', 'RecorderID']] = metaprofiles.loc[:,['UoM', 'RecorderID',]].apply(pd.Categorical)
    puom = getData('ProfileUnitsOfMeasure')
    cats = list(puom.loc[puom.UnitsID.isin(metaprofiles['UoM'].cat.categories), 'Description'])
    metaprofiles['UoM'].cat.categories = cats

    if units is None:
        plist = metaprofiles['ProfileId']
    elif units in ['V','A','kVA','kW']:
        uom = units.strip() + ' avg'
        plist = metaprofiles[metaprofiles.UoM == uom]['ProfileId']
    elif units=='Hz':
        uom = 'Hz'
        plist = metaprofiles[metaprofiles.UoM == uom]['ProfileId']
    else:
        return print('Check spelling and choose V, A, kVA, Hz or kW as units, or leave blank to get profiles of all.')
    return metaprofiles, plist

def profileFetchEst(year):
    """
    This function estimates the number of profiles, fetch time and memory usage to get all profiles for a year.
    
    """
    plist = list(map(str, getProfileID(year))) 
    profs = len(plist)
    profilefetch = profs*0.7/60
    profilesize = profs*2.69
    print('It will take %f minutes to fetch all %d profiles from %d.' % (profilefetch, profs, year))
    print('The estimated memory usage is %d MB.' % (profilesize))

def getProfiles(year, month = None, units = None):
    """
    This function fetches load profiles for one calendar year. 
    It takes the year as number and units as string [A, V, kVA, Hz, kW] as input.
    
    """
    ## Get metadata
    mp, plist = getMetaProfiles(year, units = None)
    
    ## Get profiles from server
    subquery = ', '.join(str(x) for x in plist)
    for i in range(1,12):
        try:
            query = "SELECT pt.ProfileID \
             ,pt.Datefield \
             ,pt.Unitsread \
             ,pt.Valid \
            FROM [General_LR4].[dbo].[Profiletable] pt \
            WHERE pt.ProfileID IN " + subquery + " AND MONTH(Datefield) =" + str(i) + "\
            ORDER BY pt.Datefield, pt.ProfileID"
            profiles = getData(querystring = query)
            #profiles['Valid'] = profiles['Valid'].map(lambda x: x.strip()).map({'Y':True, 'N':False}) #reduce memory usage
        
            #data output:    
            df = pd.merge(profiles, mp, left_on='ProfileID', right_on='ProfileId')
            df.drop('ProfileId', axis=1, inplace=True)
            #convert strings to category data type to reduce memory usage
            df.loc[:,['ProfileID','Valid']] = df.loc[:,['ProfileID','Valid']].apply(pd.Categorical)
        except:
            pass

    return df

def getSampleProfiles(year):
    """
    This function provides a sample of the top 1000 rows that will be returned with the getProfiles() function
    
    """
    ## Get metadata
    mp, plist = getMetaProfiles(year, units = None)
    mp = mp[0:9]
    plist = plist[0:9]
    
    ## Get profiles from server
    subquery = ', '.join(str(x) for x in plist) #' OR pt.ProfileID = '.join(plist.map(lambda x: str(x)))
    query = "SELECT TOP 1000 pt.ProfileID, pt.Datefield, pt.Unitsread, pt.Valid FROM [General_LR4].[dbo].[Profiletable] pt WHERE (pt.ProfileID = " + subquery + ") ORDER BY pt.Datefield, pt.ProfileID"
    profiles = getData(querystring = query)
    profiles['Valid'] = profiles['Valid'].map(lambda x: x.strip()).map({'Y':True, 'N':False}) #reduce memory usage

    ## Create data output    
    df = pd.merge(profiles, mp, left_on='ProfileID', right_on='ProfileId')
    df.drop('ProfileId', axis=1, inplace=True)
    df.loc[:,['ProfileID']] = df.loc[:,['ProfileID']].apply(pd.Categorical)     #convert to category type to reduce memory

    ## Provide memory and time estimate for fetching all profiles for the year    
    profileFetchEst(year)
    
    return df

def profilePeriod(dataframe, startdate = None, enddate = None):
    """
    This function selects a subset of a profile dataframe based on a date range. Use getProfiles or upload profiles data. 
    Dates must be formated as 'YYYY-MM-DD'. Days start at 00:00 and end at 23:55
    
    """
    #print profile date info
    dataStart = dataframe['Datefield'].min()
    dataEnd = dataframe['Datefield'].max()
    print('Profile starts on %s. \nProfile ends on %s.' % (dataStart, dataEnd))
    
    #prompt for user input if no start and end dates were provided
    startdate = input('Enter period start date as YYYY-MM-DD\n') if startdate is None else startdate
    enddate = input('Enter period end date as YYYY-MM-DD\n') if enddate is None else enddate
    
    #convert start and end date user input to datetime object
    if isinstance(startdate, str):
        startdate = datetime.strptime(startdate + ' 00:00', '%Y-%m-%d %H:%M')
    if isinstance(enddate, str):
        enddate = datetime.strptime(enddate + ' 23:55', '%Y-%m-%d %H:%M')
    
    #check that input dates fall within the profile period
    if startdate > enddate :
        return print('Period start must be before period end.')
    if datetime.date(startdate) == datetime.date(dataStart): #set start date to data start to avoid time error
        startdate = dataStart
    if datetime.date(enddate) == datetime.date(dataEnd): #set end date to data end to avoid time error
        enddate = dataEnd
    if (startdate < dataStart) | (startdate > dataEnd):
        return print('This profile starts on %s and ends on %s. Choose a start date that falls within this period.' % (dataStart, dataEnd))
    if (enddate < dataStart) | (enddate > dataEnd):
        return print('This profile starts on %s and ends on %s. Choose an end date that falls within this period.' % (dataStart, dataEnd))
    
    #subset dataframe by the specified date range
    df = dataframe.loc[(dataframe['Datefield'] >= startdate) & (dataframe['Datefield'] <= enddate)].reset_index(drop=True)
    #convert strings to category data type to reduce memory usage
    #df.loc[:,['AnswerID', 'ProfileID', 'Description', 'RecorderID', 'Valid']] = df.loc[:,['AnswerID', 'ProfileID', 'Description', 'RecorderID', 'Valid']].apply(pd.Categorical)
    return df

def getGroups(year = None):
    """
    This function performs some massive Groups wrangling
    
    """
    groups = getData('Groups')
    groups['ParentID'].fillna(0, inplace=True)
    groups['ParentID'] = groups['ParentID'].astype('int64').astype('category')
    groups['GroupName'] = groups['GroupName'].map(lambda x: x.strip())
    #TRY THIS groups['GroupName'] = groups['GroupName'].str.strip()
    
    #Deconstruct groups table apart into levels
    #LEVEL 1 GROUPS: domestic/non-domestic
    groups_level_1 = groups[groups['ParentID']==0] 
    #LEVEL 2 GROUPS: Eskom LR, NRS LR, Namibia, Clinics, Shops, Schools
    groups_level_2 = groups[groups['ParentID'].isin(groups_level_1['GroupID'])]
    #LEVLE 3 GROUPS: Years
    groups_level_3 = groups[groups['ParentID'].isin(groups_level_2['GroupID'])]
    #LEVLE 4 GROUPS: Locations
    groups_level_4 = groups[groups['ParentID'].isin(groups_level_3['GroupID'])]
    
    #Slim down the group levels to only include columns requried for merging
    g1 = groups.loc[groups['ParentID']==0,['GroupID','ParentID','GroupName']].reset_index(drop=True)
    g2 = groups.loc[groups['ParentID'].isin(groups_level_1['GroupID']), ['GroupID','ParentID','GroupName']].reset_index(drop=True)
    g3 = groups.loc[groups['ParentID'].isin(groups_level_2['GroupID']), ['GroupID','ParentID','GroupName']].reset_index(drop=True)
    
    #reconstruct group levels as one pretty, multi-index table
    recon3 = pd.merge(groups_level_4, g3, left_on ='ParentID', right_on = 'GroupID' , how='left', suffixes = ['_4','_3'])
    recon2 = pd.merge(recon3, g2, left_on ='ParentID_3', right_on = 'GroupID' , how='left', suffixes = ['_3','_2'])
    recon1 = pd.merge(recon2, g1, left_on ='ParentID', right_on = 'GroupID' , how='left', suffixes = ['_2','_1'])
    prettyg = recon1[['ContextID','GroupID_1','GroupID_2','GroupID_3','GroupID_4','GroupName_1','GroupName_2','GroupName_3','GroupName_4']]
    prettynames = ['ContextID', 'GroupID_1','GroupID_2','GroupID_3','GroupID','Dom_NonDom','Survey','Year','Location']
    prettyg.columns = prettynames
    
    #create multi-index dataframe
    allgroups = prettyg.set_index(['GroupID_1','GroupID_2','GroupID_3']).sort_index()
    
    if year is None:
        return allgroups
    #filter dataframe on year
    else:
        stryear = str(year)
        return allgroups[allgroups['Year']== stryear] 

def saveTables(names, dataframes): 
    """
    This function saves a dictionary of name:dataframe items from a list of names and a list of dataframes as feather files.
    The getData() and getGroups() functions can be used to construct the dataframes.
    
    """
    datadict = dict(zip(names, dataframes))
    for k in datadict.keys():
        data = datadict[k].fillna(np.nan) #feather doesn't write None type
        os.makedirs(os.path.join(parent_dir, 'data', 'tables') , exist_ok=True)
        path = os.path.join(parent_dir, 'data', 'tables', k + '.feather')
        feather.write_dataframe(data, path)
    return

def saveAllProfiles(mypath, yearstart, yearend):
    """
    This function fetches all profile data and saves it to path as a .feather file. 
    ATTENTION: It will take several hours to run!
    
    """
    for i in range(yearstart, yearend + 1):
        print(i)
        df = getProfiles(i)
        path = mypath + 'p' + str(i) + '.feather'
        print(path)
        feather.write_dataframe(df, path)
        
def anonAns():
    """
    This function fetches survey responses and anonymises them, then returns and saves the anonymsed dataset as feather object
    
    """
    anstables = {'Answers_blob':'blobQs.csv', 'Answers_char':'charQs.csv'}    
    for k,v in anstables.items():
        a = getData(k) #get all answers
        qs = pd.read_csv(os.path.join(parent_dir,'data','anonymise', v))
        qs = qs.loc[lambda qs: qs.anonymise == 1, :]
        qanon = pd.merge(getData('Answers'), qs, left_on='QuestionaireID', right_on='QuestionaireID')[['AnswerID','ColumnNo','anonymise']]
        
        for i, rows in qanon.iterrows():
            a.set_value(a[a.AnswerID == rows.AnswerID].index[0], str(rows.ColumnNo),'a')
        
        saveTables([k.lower() + '_anon'],[a]) #saves answers as feather object
    return