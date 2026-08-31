Melting Point Experimental Data Portal
======================================

First-time setup
----------------

1. Install Python 3.10 or 3.11 (64-bit).

2. Open a terminal in this project folder.

3. Install the required Python packages:

   python -m pip install -r requirements.txt


Starting the application
------------------------

Double-click:

   Start_Melting_Point_Portal.bat

The application will open automatically in your web browser.

Default local address:

   http://localhost:8501


rf IDEAS card reader
--------------------

For student card functionality:

1. Connect the rf IDEAS WAVE ID Plus reader via USB.
2. Close rf IDEAS Configuration Utility if it is running.
3. Start the portal.
4. Use the Scan Card buttons inside the portal.


Experiment workflow
-------------------

1. Students
   Register a student and scan their student card.

2. Create Experiment Run
   Select or scan the student and upload the Optimelt OPM file.

3. Import Person 2 Data
   Upload:
   - Calibrated Results CSV
   - RawData CSV

4. Assign Material Names
   Enter the actual material names for Left, Centre and Right.

5. Material Recommendation
   Enter a predicted melting point to obtain the two closest
   historical materials based on corrected Clear Point.

6. Admin Viewer
   View all experiment records and melting image sequences.

7. Student Access
   Scan a registered student card to view that student's experiments.


Stopping the application
------------------------

To stop the application, close the command window.
